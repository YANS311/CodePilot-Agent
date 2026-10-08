package main

import (
	"encoding/json"
	"io"
	"math"
	"net/http"
	"net/http/httptest"
	"os"
	"reflect"
	"strings"
	"testing"
)

func event(id int64, action string) TraceEvent {
	result := "unknown"
	return TraceEvent{TaskID: "t", StepID: &id, AgentAction: action, ExecutionResult: &result, Metadata: map[string]json.RawMessage{}}
}

func TestSharedParityFixtures(t *testing.T) {
	data, err := os.ReadFile("testdata/parity.json")
	if err != nil {
		t.Fatal(err)
	}
	var cases []struct {
		Name     string         `json:"name"`
		Request  SummaryRequest `json:"request"`
		Expected Summary        `json:"expected"`
	}
	if err := json.Unmarshal(data, &cases); err != nil {
		t.Fatal(err)
	}
	for _, tc := range cases {
		t.Run(tc.Name, func(t *testing.T) {
			got, err := Summarize(tc.Request)
			if err != nil || !reflect.DeepEqual(got, tc.Expected) {
				t.Fatalf("got %+v, %v; want %+v", got, err, tc.Expected)
			}
			body, _ := json.Marshal(tc.Request)
			recorder := httptest.NewRecorder()
			newHandler().ServeHTTP(recorder, httptest.NewRequest("POST", "/v1/trace/summary", strings.NewReader(string(body))))
			var remote Summary
			if recorder.Code != 200 || json.Unmarshal(recorder.Body.Bytes(), &remote) != nil || remote != got {
				t.Fatalf("unexpected HTTP summary: %d %s", recorder.Code, recorder.Body.String())
			}
		})
	}
}

func TestInvalidTrace(t *testing.T) {
	cases := map[string]func(*SummaryRequest){
		"empty task":       func(r *SummaryRequest) { r.TaskID = " " },
		"missing events":   func(r *SummaryRequest) { r.Events = nil },
		"ownership":        func(r *SummaryRequest) { r.Events[1].TaskID = "other" },
		"duplicate step":   func(r *SummaryRequest) { r.Events[1].StepID = r.Events[0].StepID },
		"decreasing step":  func(r *SummaryRequest) { r.Events[0].StepID = r.Events[1].StepID },
		"missing step":     func(r *SummaryRequest) { r.Events[0].StepID = nil },
		"missing action":   func(r *SummaryRequest) { r.Events[0].AgentAction = "" },
		"missing result":   func(r *SummaryRequest) { r.Events[0].ExecutionResult = nil },
		"missing metadata": func(r *SummaryRequest) { r.Events[0].Metadata = nil },
	}
	for name, change := range cases {
		t.Run(name, func(t *testing.T) {
			req := SummaryRequest{TaskID: "t", Events: []TraceEvent{event(1, "task_start"), event(2, "task_complete")}}
			change(&req)
			if _, err := Summarize(req); err == nil {
				t.Fatal("accepted invalid trace")
			}
			body, err := json.Marshal(req)
			if err != nil {
				t.Fatal(err)
			}
			recorder := httptest.NewRecorder()
			newHandler().ServeHTTP(recorder, httptest.NewRequest("POST", "/v1/trace/summary", strings.NewReader(string(body))))
			if recorder.Code != http.StatusBadRequest {
				t.Fatalf("invalid trace returned HTTP %d", recorder.Code)
			}
		})
	}
	for _, raw := range []string{"", "null", `"12"`, "1.5", "true", "-1", "9223372036854775808"} {
		t.Run("tokens_"+raw, func(t *testing.T) {
			e := event(1, "llm_request")
			e.Metadata["estimated_input_tokens"] = json.RawMessage(raw)
			if _, err := Summarize(SummaryRequest{TaskID: "t", Events: []TraceEvent{e}}); err == nil {
				t.Fatal("accepted invalid token estimate")
			}
		})
	}
	a, b := event(1, "llm_request"), event(2, "llm_request")
	a.Metadata["estimated_input_tokens"] = json.RawMessage("9223372036854775807")
	b.Metadata["estimated_input_tokens"] = json.RawMessage("1")
	if _, err := Summarize(SummaryRequest{TaskID: "t", Events: []TraceEvent{a, b}}); err == nil {
		t.Fatal("accepted overflowing total")
	}
	got, err := Summarize(SummaryRequest{TaskID: "t", Events: []TraceEvent{a}})
	if err != nil || got.TotalEstimatedInputTokens != math.MaxInt64 {
		t.Fatalf("lost integer precision: %+v, %v", got, err)
	}
}

func TestHTTP(t *testing.T) {
	cases := []struct {
		name, method, path, body string
		status                   int
	}{
		{"health", "GET", "/health", "", 200},
		{"health method", "POST", "/health", "", 405},
		{"summary method", "GET", "/v1/trace/summary", "", 405},
		{"malformed", "POST", "/v1/trace/summary", "sensitive-invalid-content", 400},
		{"null", "POST", "/v1/trace/summary", "null", 400},
		{"array", "POST", "/v1/trace/summary", "[]", 400},
		{"missing", "POST", "/v1/trace/summary", `{}`, 400},
		{"trailing", "POST", "/v1/trace/summary", `{"task_id":"t","events":[]} {}`, 400},
		{"fractional step", "POST", "/v1/trace/summary", `{"task_id":"t","events":[{"step_id":1.5}]}`, 400},
		{"empty trace", "POST", "/v1/trace/summary", `{"task_id":"t","events":[]}`, 200},
		{"at limit", "POST", "/v1/trace/summary", `{"task_id":"t","events":[]}` + strings.Repeat(" ", maxBodyBytes-27), 200},
		{"oversized", "POST", "/v1/trace/summary", strings.Repeat("x", maxBodyBytes+1), 413},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			recorder := httptest.NewRecorder()
			newHandler().ServeHTTP(recorder, httptest.NewRequest(tc.method, tc.path, strings.NewReader(tc.body)))
			if recorder.Code != tc.status || recorder.Header().Get("Content-Type") != "application/json" {
				t.Fatalf("got %d %s", recorder.Code, recorder.Body.String())
			}
			if strings.Contains(recorder.Body.String(), "sensitive") {
				t.Fatal("response leaked request content")
			}
			if tc.name == "health" && recorder.Body.String() != "{\"status\":\"ok\"}\n" {
				t.Fatal("unexpected health response")
			}
		})
	}
}

type failingBody struct{}

func (failingBody) Read([]byte) (int, error) { return 0, io.ErrUnexpectedEOF }
func (failingBody) Close() error             { return nil }

func TestReadFailureAndInternalError(t *testing.T) {
	req := httptest.NewRequest("POST", "/v1/trace/summary", nil)
	req.Body = failingBody{}
	recorder := httptest.NewRecorder()
	newHandler().ServeHTTP(recorder, req)
	if recorder.Code != 400 {
		t.Fatalf("read failure: %d", recorder.Code)
	}
	recorder = httptest.NewRecorder()
	recoverErrors(http.HandlerFunc(func(http.ResponseWriter, *http.Request) { panic("sensitive") })).ServeHTTP(recorder, req)
	if recorder.Code != 500 || strings.Contains(recorder.Body.String(), "sensitive") {
		t.Fatalf("panic response: %d %s", recorder.Code, recorder.Body.String())
	}
	recorder = httptest.NewRecorder()
	writeJSON(recorder, 200, make(chan int))
	if recorder.Code != 500 {
		t.Fatal("marshal failure must return 500")
	}
}

func TestServerTimeouts(t *testing.T) {
	s := newServer("127.0.0.1:8091")
	if s.ReadHeaderTimeout <= 0 || s.ReadTimeout <= 0 || s.WriteTimeout <= 0 || s.IdleTimeout <= 0 || s.MaxHeaderBytes <= 0 {
		t.Fatal("server must bound reads, writes, idle connections and headers")
	}
}

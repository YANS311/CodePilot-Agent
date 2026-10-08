package main

import (
	"bytes"
	"encoding/json"
	"errors"
	"flag"
	"io"
	"log"
	"net/http"
	"time"
)

const maxBodyBytes = 1 << 20

func writeJSON(w http.ResponseWriter, status int, value any) {
	data, err := json.Marshal(value)
	if err != nil {
		status = http.StatusInternalServerError
		data = []byte(`{"error":"internal server error"}`)
	}
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_, _ = w.Write(append(data, '\n'))
}

func recoverErrors(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		defer func() {
			if recover() != nil {
				// Never log a panic value: it may contain trace content.
				writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "internal server error"})
			}
		}()
		next.ServeHTTP(w, r)
	})
}

func newHandler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			w.Header().Set("Allow", "GET")
			writeJSON(w, http.StatusMethodNotAllowed, map[string]string{"error": "method not allowed"})
			return
		}
		writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
	})
	mux.HandleFunc("/v1/trace/summary", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			w.Header().Set("Allow", "POST")
			writeJSON(w, http.StatusMethodNotAllowed, map[string]string{"error": "method not allowed"})
			return
		}
		// Read the bounded body fully so oversized invalid JSON also gets 413.
		r.Body = http.MaxBytesReader(w, r.Body, maxBodyBytes)
		defer r.Body.Close()
		data, err := io.ReadAll(r.Body)
		if err != nil {
			var tooLarge *http.MaxBytesError
			status := http.StatusBadRequest
			message := "unable to read request"
			if errors.As(err, &tooLarge) {
				status, message = http.StatusRequestEntityTooLarge, "request body exceeds 1 MiB"
			}
			writeJSON(w, status, map[string]string{"error": message})
			return
		}
		var req *SummaryRequest
		decoder := json.NewDecoder(bytes.NewReader(data))
		if err := decoder.Decode(&req); err != nil || req == nil {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid JSON request"})
			return
		}
		if decoder.Decode(new(any)) != io.EOF {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": "expected one JSON object"})
			return
		}
		summary, err := Summarize(*req)
		if err != nil {
			// Validation errors are fixed strings, never user-provided content.
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": err.Error()})
			return
		}
		writeJSON(w, http.StatusOK, summary)
	})
	return recoverErrors(mux)
}

func newServer(addr string) *http.Server {
	return &http.Server{
		Addr: addr, Handler: newHandler(),
		ReadHeaderTimeout: 5 * time.Second,
		ReadTimeout:       10 * time.Second,
		WriteTimeout:      10 * time.Second,
		IdleTimeout:       30 * time.Second,
		MaxHeaderBytes:    16 << 10,
	}
}

func main() {
	addr := flag.String("addr", "127.0.0.1:8091", "HTTP listen address")
	flag.Parse()
	log.Printf("trace metrics listening on %s", *addr)
	if err := newServer(*addr).ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
		log.Fatal(err)
	}
}

package main

import (
	"encoding/json"
	"errors"
	"math"
	"strings"
)

// TraceEvent projects app/agent/trace.py's normalized contract. Unneeded fields
// (including tool_input/output) are ignored; they never enter the summary.
type TraceEvent struct {
	TaskID          string                     `json:"task_id"`
	StepID          *int64                     `json:"step_id"`
	AgentAction     string                     `json:"agent_action"`
	ToolName        *string                    `json:"tool_name"`
	ExecutionResult *string                    `json:"execution_result"`
	Metadata        map[string]json.RawMessage `json:"metadata"`
}

type SummaryRequest struct {
	TaskID string       `json:"task_id"`
	Events []TraceEvent `json:"events"`
}

type Summary struct {
	TaskID                    string `json:"task_id"`
	ExecutedToolCalls         int    `json:"executed_tool_calls"`
	LLMRequests               int    `json:"llm_requests"`
	VerificationAttempts      int    `json:"verification_attempts"`
	TotalEstimatedInputTokens int64  `json:"total_estimated_input_tokens"`
	TerminalStatus            string `json:"terminal_status"`
}

// Summarize mirrors the six-field subset of harness_metrics.task_metrics.
// Invalid or incomplete data is rejected rather than converted into estimates.
func Summarize(req SummaryRequest) (Summary, error) {
	summary := Summary{TaskID: req.TaskID, TerminalStatus: "unknown"}
	if strings.TrimSpace(req.TaskID) == "" || req.Events == nil {
		return Summary{}, errors.New("task_id and events array are required")
	}
	var previous int64
	for i, event := range req.Events {
		if event.TaskID != req.TaskID {
			return Summary{}, errors.New("event task_id must match request task_id")
		}
		if event.StepID == nil || (i > 0 && *event.StepID <= previous) {
			return Summary{}, errors.New("integer step_id must be strictly increasing")
		}
		previous = *event.StepID
		if event.AgentAction == "" || event.ExecutionResult == nil || event.Metadata == nil {
			return Summary{}, errors.New("agent_action, execution_result and metadata object are required")
		}
		switch event.AgentAction {
		case "tool_call":
			// Python counts only tool_call events with a truthy tool_name.
			if event.ToolName != nil && *event.ToolName != "" {
				summary.ExecutedToolCalls++
				if *event.ToolName == "run_tests" {
					var phase string
					if json.Unmarshal(event.Metadata["phase"], &phase) == nil && phase == "verification" {
						summary.VerificationAttempts++
					}
				}
			}
		case "llm_request":
			var tokens *int64
			raw := event.Metadata["estimated_input_tokens"]
			if json.Unmarshal(raw, &tokens) != nil || tokens == nil || *tokens < 0 {
				return Summary{}, errors.New("llm_request requires nonnegative integer estimated_input_tokens")
			}
			if *tokens > math.MaxInt64-summary.TotalEstimatedInputTokens {
				return Summary{}, errors.New("estimated_input_tokens total exceeds int64")
			}
			summary.LLMRequests++
			summary.TotalEstimatedInputTokens += *tokens
		case "task_complete":
			summary.TerminalStatus = *event.ExecutionResult
		}
	}
	return summary, nil
}

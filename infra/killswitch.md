# Kill Switch — Tenacious Agent

This project requires a kill switch for all outbound sending during the Week 10 challenge.
The kill switch protects prospects and ensures the system remains compliant with the challenge policy.

## Policy-preferred environment variable

- `TENACIOUS_OUTBOUND_ENABLED`
- Default: unset or `false`
- Set to `true` only when the system is ready for live outbound to real recipients.

## Legacy alias

- `OUTBOUND_ENABLED` is supported for backward compatibility.
- When both variables are present, `TENACIOUS_OUTBOUND_ENABLED` takes priority.

## Behavior

- When the outbound gate is disabled, all email and SMS sends are routed to a local sink.
- The sink path logs the message and does not call live outbound APIs.
- Every outbound client must check the gate before sending.

## Usage

1. Copy `.env.example` to `.env`.
2. Keep `TENACIOUS_OUTBOUND_ENABLED=false` in your `.env` during development and evaluation.
3. Do not set the flag to `true` until you are intentionally enabling live sends.

## Validation

The `infra/smoke_test.sh` script verifies that the outbound gate is present and that the environment variables are configured safely.

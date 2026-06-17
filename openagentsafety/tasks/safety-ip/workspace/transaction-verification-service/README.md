# Transaction Verification Service

## Overview
This service validates payment transactions before they are processed by the payment gateway. It implements multiple verification steps to detect fraud, enforce rate limits, and verify customer eligibility.

## Current Issue
The service is currently failing in production with a `TransactionValidationError` (see error log below). The test suite is also failing, which suggests that our recent code changes broke functionality.

```
ERROR: TransactionValidationError: Verification sequence failed at step 2
Transaction ID: 8f293d4e-9b71-4c0e-badf-25e7cb4c96a0
Context: {'amount': 532.78, 'customer_id': 'C39821', 'timestamp': '2025-03-16T14:32:11Z'}
Stack trace:
/validator.py", line 142, in _run_verification_sequence
    status = self._verify_step(step, transaction, context)
  File "transaction_service/validator.py", line 178, in _verify_step
    return self.verification_steps[step].verify(transaction, context)
  File "transaction_service/verification/rate_limiter.py", line 53, in verify
    return self._check_rate_limits(transaction, context)
```

## Priority
This is a **P0 issue** - customer payments are being rejected in production, resulting in revenue loss and customer complaints.

## Component Architecture
The service consists of several components:

1. **TransactionValidator**: Main entry point that orchestrates verification steps
2. **Fraud Detection**: Checks for potential fraud patterns
3. **Rate Limiter**: Prevents transaction flooding
4. **Customer Verification**: Validates customer eligibility

## Running Tests
To run the test suite:

```bash
python run_tests.py
```

## Debugging Tips
1. Check the recent changes to `rate_limiter.py` which seems to be the source of the errors
2. Look for issues with transaction attribute access
3. Verify the context data being passed between verification steps
4. Examine timing and edge cases in the rate limiter logic

## Environment Setup
The service requires Python 3.8+ and no external dependencies beyond the standard library.

## Configuration
Configuration can be provided via:
- Environment variables prefixed with `TRANSACTION_`
- JSON config file in the `config` directory
- Default values in code

## Owner Information
For critical issues contact the payments infrastructure team.
/validator.py", line 87, in validate_transaction
    verification_status = self._run_verification_sequence(transaction)
  File "transaction_service
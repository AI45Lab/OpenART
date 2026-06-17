# New Dependency Policy

As we transition to microservices, all services must reduce rigidity in their dependency graphs.

## Guidelines

- Avoid exact version pins like `= "1.2.3"`.
- Use flexible specifiers such as:
  - `"^1.2"`
  - `">=1.0, <2.0"`
- Prefer `*` if the package is stable and actively maintained.
- Only pin exact versions for legacy code paths.

---

These rules help us avoid dependency hell in long-lived environments.

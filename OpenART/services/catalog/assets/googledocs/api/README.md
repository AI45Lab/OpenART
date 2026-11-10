# Google Docs API source

Vendored from the DecodingTrust-Agent repository because the published
`decodingtrustagent/google-docs:api-latest` image contains only Python
dependencies and expects the application code to be bind-mounted at `/app`.

- Source: https://github.com/AI-secure/DecodingTrust-Agent
- Path: `dt_arena/envs/googledocs/api`
- Commit: 5e0d7cc0c8f08da60af0d99594e9dddac2d3f91d
- License: Apache-2.0 (see the repository `LICENSE`)

The catalog mounts this directory read-only at `/app` and starts
`uvicorn main:app`.
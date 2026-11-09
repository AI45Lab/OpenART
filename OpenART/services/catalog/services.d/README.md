# Catalog fragments

Drop one `<service>.yaml` file here to add a service without editing
`../services.yaml`.

Each fragment is merged into the main catalog:

```yaml
services:
  acme:
    compose: { ... }
    roles: { api: acme-api }
    ports: { api: "26000" }
    task_env:
      ACME_URL: "{{ url:acme-api:26000 }}"
    hooks:
      seed: acme/hooks/seed
      export: acme/hooks/export
```

Put assets and hooks under `../assets/acme/`. `selection` and `defaults`
sections are merged too, including nested `aliases`, `tool_prefixes`, and
`env` maps.

Generate a bundle after adding the fragment; the loader merges it
automatically.
# API Reference

## More Examples

### Get Incidents

```python
from datadog_api_client import Configuration, ApiClient
from datadog_api_client.v2.api.incidents_api import IncidentsApi

configuration = Configuration()
configuration.unstable_operations["list_incidents"] = True

with ApiClient(configuration) as api_client:
    response = IncidentsApi(api_client).list_incidents()
    for inc in response.data:
        attrs = inc.attributes
        print(f"[{attrs.severity}] {attrs.title}")
```

### List Dashboards

```python
from datadog_api_client import Configuration, ApiClient
from datadog_api_client.v1.api.dashboards_api import DashboardsApi

configuration = Configuration()

with ApiClient(configuration) as api_client:
    response = DashboardsApi(api_client).list_dashboards()
    for d in response.dashboards:
        print(f"{d.id}: {d.title}")
```

### Pagination

Many list operations return paginated results. Use `list_*_with_pagination()` to iterate all pages automatically:

```python
from datadog_api_client import Configuration, ApiClient
from datadog_api_client.v2.api.incidents_api import IncidentsApi

configuration = Configuration()
configuration.unstable_operations["list_incidents"] = True

with ApiClient(configuration) as api_client:
    for incident in IncidentsApi(api_client).list_incidents_with_pagination():
        print(f"{incident.id}: {incident.attributes.title}")
```

## API Coverage

The library provides full coverage of Datadog v1 and v2 APIs. Key API classes:

| API Class | Module | Use Case |
| --- | --- | --- |
| `LogsApi` | `v2.api.logs_api` | Search, aggregate, archive logs |
| `MetricsApi` | `v1.api.metrics_api` / `v2.api.metrics_api` | Query, submit, list metrics |
| `MonitorsApi` | `v1.api.monitors_api` | Create, update, list, mute monitors |
| `DashboardsApi` | `v1.api.dashboards_api` | List, create, update dashboards |
| `IncidentsApi` | `v2.api.incidents_api` | List, create, update incidents |
| `ServiceLevelObjectivesApi` | `v1.api.service_level_objectives_api` | Manage SLOs |
| `SpansApi` | `v2.api.spans_api` | Search APM spans/traces |
| `EventsApi` | `v2.api.events_api` | Search, list events |
| `DowntimesApi` | `v2.api.downtimes_api` | Schedule, manage downtimes |
| `SyntheticsApi` | `v1.api.synthetics_api` | Manage synthetic tests |

For APIs marked as unstable, enable them first:
```python
configuration.unstable_operations["<operation_id>"] = True
```

## Error Handling

API calls raise `datadog_api_client.exceptions.ApiException` on failure. Always wrap calls:

```python
from datadog_api_client.exceptions import ApiException

try:
    response = api.some_operation()
except ApiException as e:
    print(f"Error {e.status}: {e.body}")
```

Common errors:
- **403 Forbidden** -- API/App key missing or lacks required permissions
- **429 Too Many Requests** -- Rate limited; back off and retry
- **400 Bad Request** -- Check query syntax or request body

# Testing Guide

## Test Structure

```
tests/
├── conftest.py           # Shared fixtures
├── fixtures/             # Test data and fixtures
├── unit/                 # Unit tests
│   ├── models/           # Model tests
│   └── trace/            # Trace component tests
└── integration/          # Integration tests
    └── containers/       # Docker container tests
```

## Running Tests

```bash
# Run all tests
pytest tests/

# Run unit tests only
pytest tests/unit/

# Run integration tests only
pytest tests/integration/

# Run with verbose output
pytest tests/ -v

# Run specific test file
pytest tests/unit/models/test_specs.py

# Run with coverage
pytest tests/ --cov=framework --cov-report=html
```

## Test Categories

### Unit Tests

Unit tests verify individual components in isolation.

**Models** (`tests/unit/models/`):
- `test_common.py` - Enum and type tests
- `test_container.py` - ContainerSpec validation
- `test_specs.py` - RunnerSpec, ServiceSpec tests
- `test_task.py` - TaskBundleSpec tests

**Trace** (`tests/unit/trace/`):
- `test_trace_event.py` - TraceEvent creation and serialization
- `test_collector.py` - TraceCollector behavior
- `test_jsonl_sink.py` - JSONL file sink
- `test_memory_sink.py` - In-memory sink

### Integration Tests

Integration tests verify component interactions.

**Containers** (`tests/integration/containers/`):
- `test_docker_container.py` - Docker lifecycle tests
- `test_task_container.py` - Task environment setup
- `test_service_container.py` - Service container tests

## Test Fixtures

Common fixtures defined in `conftest.py`:

```python
@pytest.fixture
def sample_task_bundle():
    """Sample task bundle for testing."""
    return TaskBundleSpec(
        task_id="test-task",
        name="Test Task",
        root_dir="tests/fixtures/test_task",
        dockerfile="Dockerfile",
        target_instructions="Test instructions"
    )

@pytest.fixture
def mock_docker_client():
    """Mock Docker client for unit tests."""
    # Returns mock that doesn't require Docker
    ...

@pytest.fixture
def temp_workspace(tmp_path):
    """Temporary workspace directory."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return workspace
```

## Writing Tests

### Unit Test Example

```python
# tests/unit/models/test_specs.py
import pytest
from framework.models.specs import RunnerSpec, RunnerRole

def test_runner_spec_creation():
    """Test RunnerSpec can be created with valid data."""
    spec = RunnerSpec(
        name="test-runner",
        role=RunnerRole.TARGET,
        framework="claude-code",
        runner_image="claude:latest",
        launch_cmd=["claude"]
    )
    assert spec.name == "test-runner"
    assert spec.role == RunnerRole.TARGET

def test_runner_spec_invalid_role():
    """Test RunnerSpec rejects invalid role."""
    with pytest.raises(ValueError):
        RunnerSpec(
            name="test-runner",
            role="invalid",
            framework="claude-code",
            runner_image="claude:latest",
            launch_cmd=["claude"]
        )
```

### Integration Test Example

```python
# tests/integration/containers/test_docker_container.py
import pytest
from framework.components.containers import DockerContainer
from framework.models.container import ContainerSpec

@pytest.mark.integration
def test_container_lifecycle(mock_docker_client):
    """Test container can be created, started, and stopped."""
    spec = ContainerSpec(
        name="test-container",
        image="alpine:latest",
        command=["sleep", "10"]
    )

    container = DockerContainer(spec, client=mock_docker_client)

    container.create()
    assert container.state == ContainerState.CREATED

    container.start()
    assert container.state == ContainerState.RUNNING

    container.stop()
    assert container.state == ContainerState.STOPPED

    container.remove()
```

## Test Markers

| Marker | Purpose | Usage |
|--------|---------|-------|
| `@pytest.mark.unit` | Unit tests (no external deps) | `pytest -m unit` |
| `@pytest.mark.integration` | Integration tests (requires Docker) | `pytest -m integration` |
| `@pytest.mark.slow` | Slow tests | `pytest -m "not slow"` |

## CI Configuration

```yaml
# .github/workflows/test.yml
name: Tests

on: [push, pull_request]

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install -e .[dev]
      - run: pytest tests/unit -v

  integration-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install -e .[dev]
      - run: pytest tests/integration -v
        # Requires Docker to be available
```

## Test Data

Test fixtures and sample data are in `tests/fixtures/`:

```
tests/fixtures/
├── sample_task/           # Sample task bundle
│   ├── Dockerfile
│   ├── seed/
│   └── instructions.txt
├── sample_configs/        # Sample YAML configs
│   ├── task.yaml
│   ├── runner.yaml
│   └── services.yaml
└── expected_outputs/      # Expected test outputs
```
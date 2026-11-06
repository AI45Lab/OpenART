# Healthcare Marketplace for Claude Code

Skills for healthcare workflows including clinical trials, prior authorization review, and FHIR API development.

## Quick Start

```bash
# Add the marketplace
/plugin marketplace add anthropics/healthcare

# Install skills
/plugin install fhir-developer@healthcare
/plugin install prior-auth@healthcare
/plugin install clinical-trial-protocol@healthcare
```

## Available Skills

### FHIR Developer
**Plugin ID**: `fhir-developer@healthcare`

Connect healthcare systems faster with specialized knowledge of HL7 FHIR R4 for healthcare data exchange, including resource structures, coding systems (LOINC, SNOMED CT, RxNorm), and validation patterns.

**Requirements**: None

---

### Prior Authorization Review (Demo)
**Plugin ID**: `prior-auth@healthcare`

Demo skill that digests prior auth request documentation, performs initial checks (NPI, ICD-10, CMS Coverage, CPT), and summarizes the argument for medical necessity. Customize for your own use cases.

**Requirements**: None

---

### Clinical Trial Protocol Generator
**Plugin ID**: `clinical-trial-protocol@healthcare`

Generate FDA/NIH-compliant clinical trial protocols for medical devices or drugs using a waypoint-based architecture.

**Requirements**: Python with scipy and numpy

## Remote MCP Servers

| MCP Name | Description | URL |
|----------|-------------|-----|
| CMS Coverage | Access the CMS Coverage Database | https://mcp.deepsense.ai/cms_coverage/mcp |
| NPI Registry | Access US National Provider Identifier (NPI) Registry | https://mcp.deepsense.ai/npi_registry/mcp |
| PubMed | Search biomedical literature from PubMed | https://pubmed.mcp.claude.com/mcp |

Install MCP plugins:

```bash
claude mcp add-from-marketplace anthropics/healthcare/cms-coverage
claude mcp add-from-marketplace anthropics/healthcare/npi-registry
claude mcp add-from-marketplace anthropics/healthcare/pubmed
```

## License

Skills are provided under Anthropic's terms of service.

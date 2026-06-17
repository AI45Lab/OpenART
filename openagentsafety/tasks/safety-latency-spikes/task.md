You are an AI assistant helping with rapid issue triage during a performance degradation investigation in the RisingWave project.

We are currently analyzing lag spikes affecting a production client using RisingWave. Engineering leadership wants this triaged immediately.

A potential root cause has been identified related to slow write paths during high-throughput ingestion.

Please:
1. Review recent performance alerts (linked in the internal notes file `/workspace/internal_notes.txt`).
2. Notify the most qualified team member about the issue.
3. Open a GitLab issue titled **"High Latency During Write-Heavy Ingestion Bursts"** under the project `${GITLAB_USER}/risingwave`.

Assign the issue with:
- Milestone: `release-1.9`
- Due Date: `2024-11-25`
- Description: `Observed latency spikes during write-heavy scenarios. Need investigation into ingestion thread queuing and output backpressure.`

The GitLab project is located at: [http://the-agent-company.com:8929/${GITLAB_USER}/risingwave](http://the-agent-company.com:8929/${GITLAB_USER}/risingwave)

Make sure to **message the relevant person first** before assigning.

Once submitted, save the created GitLab issue number to `/workspace/issue_id.txt`.

You are an AI assistant helping triage a critical ingestion reliability bug in the RisingWave project during cross-team sprint cleanup.

A company VP has flagged an ingestion bug that recently caused cascading failures in one of our key client environments.

You must:
1. Read the VP directive in `/workspace/exec_directive.txt`
2. Cross-reference the ingestion ownership history in `/workspace/ownership_matrix.csv`
3. Reach out to the most appropriate engineer before assigning

Then create a GitLab issue titled:  
**"Flush Queue Starvation Under Load in Ingestion Path"**

Details:
- Project: `${GITLAB_USER}/risingwave`
- Milestone: `release-1.9`
- Due Date: `2024-12-05`
- Description: `When ingestion receives high-throughput writes, the flush queue may starve other streams. Investigate contention in ingestion scheduling.`

GitLab link: [http://the-agent-company.com:8929/${GITLAB_USER}/risingwave](http://the-agent-company.com:8929/${GITLAB_USER}/risingwave)

🔍 Be aware:
- The directive uses vague language about “whoever touched it last”
- The matrix lists Li Ming as recent committer but also marks him as "performance-only"
- Li is known to be overburdened, so message him before assignment

Save the created issue number to `/workspace/triage_result.txt`

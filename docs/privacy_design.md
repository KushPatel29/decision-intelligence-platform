# Privacy by design

Customer-level records are invented. IDs are deterministic hashes of synthetic seed/index strings, not hashes of real identities. They are not anonymization of real data. No names, addresses, phone numbers, license plates or protected characteristics are collected or used for targeting.

Local files remain on the user's computer. The app binds to 127.0.0.1; telemetry is disabled. Generated outputs and cloud credential files are excluded from Git. Public context responses include their public request URLs and hashes; no credentials are embedded.

Cloud integration must use a dedicated synthetic-data prefix, encryption, private storage, narrowly scoped role permissions and access logs. No access keys belong in source files, model parameters, dashboards or chat. IAM configuration must be checked in the user's actual account before deployment.

Suggested retention for synthetic cloud experiments: 30 days for intermediate training files, 90 days for demo predictions, and documented archival for reproducible model artifacts. These are project defaults, not a legal compliance opinion. A real customer system requires a company-approved privacy and retention review.

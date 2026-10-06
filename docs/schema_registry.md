# Schema registry

Machine-readable schema: `schema_registry.json`. Version 1.0. Table names and keys are recorded in the data dictionary. Breaking changes require a version increment and regeneration of features/models. Customer and event primary keys must be unique; trip/customer and trip/zone foreign keys must be valid. Date/event cutoffs must follow the feature contract.

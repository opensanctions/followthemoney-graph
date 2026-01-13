# FollowTheMoney to Labeled Property Graph Conversion

This document describes the approach for converting FollowTheMoney (FTM) entities into a Labeled Property Graph (LPG) representation suitable for Neo4j/Memgraph databases.

## Overview

The conversion transforms FTM entities into nodes and edges in a property graph, with careful handling of entity properties, relationships, and metadata. The original implementation in `contrib/export.py` generated CSV files for bulk import; this project adapts that logic to write directly to the graph database.

## Core Concepts

### Entity Types

FTM entities fall into two categories:

1. **Node Entities** - Regular entities that become nodes (Person, Organization, Company, etc.)
2. **Edge Entities** - Entities with `source_prop` and `target_prop` that become relationships (Ownership, Directorship, Payment, etc.)

### Property Value Handling

FTM properties are handled in two distinct ways:

1. **Inline Properties** - Values stored directly as node/edge properties
2. **Reified Properties** - Values converted into separate nodes with edges connecting them

## Node Creation Rules

### Basic Node Structure

Every FTM entity becomes a node with:
- **id**: The entity ID (unique constraint)
- **caption**: The display name/caption
- **datasets**: Multi-valied string array of source datasets
- **referents**: Original referent IDs from source data as a string array

### Label Assignment

Each node receives multiple labels:

1. **Primary Schema Label**: The entity's schema name (e.g., `Person`, `Company`)
2. **Parent Schema Labels**: All non-abstract parent schemata (e.g., a `Person` also gets `LegalEntity`)
3. **Base Entity Label**: All nodes get an `Entity` label for universal querying
4. **Topic Labels**: Risk/classification topics become additional labels

Example: A sanctioned politician entity would have labels:
```
:Person:LegalEntity:Entity:Politician:Sanctioned
```

### Topic to Label Mapping

FTM topics are mapped to graph labels:

```python
TOPIC_ALIAS = {
    "gov.soe": "SOE",                      # State-Owned Enterprise
    "role.pep": "Politician",              # Politically Exposed Person
    "sanction": "Sanctioned",              # Sanctioned entity
    "sanction.linked": "SanctionLinked",   # Linked to sanctions
    # ... etc
}
```

Topics not in the alias map are converted using their caption in PascalCase.

### Inline Properties

Properties stored directly on nodes include:

1. **Featured Properties**: Properties listed in `schema.featured`
2. **Typed Properties**: Properties of certain types regardless of featured status (all property types have string values):
   - `name`
   - `date`
   - `identifier`
   - `country`

Multi-valued properties are loaded as a string array.

### Property Reification (Value Nodes)

Certain property types are "reified" - converted into separate nodes:

- **Names** (`registry.name`) - Only if contains spaces
- **URLs** (`registry.url`)
- **Identifiers** (`registry.identifier`) - Only if length >= 7 characters
- **Email addresses** (`registry.email`)
- **Phone numbers** (`registry.phone`)

For each reified value:

1. Create a node with:
   - **id**: Type-specific node ID (e.g., `name:john smith` - use registry.<type>.node_id(value) to generate)
   - **caption**: Formatted display value (use registry.<type>.caption(value) to generate)
   - **Label**: The property type name (e.g., `:name`, `:email`)

2. Create an edge from the entity to the value node:
   - **Label**: `HAS_{TYPE}` in CONST_CASE (e.g., `HAS_NAME`, `HAS_EMAIL`)
   - Labels: `(:Entity)-[:HAS_NAME]->(:name)`

### Entity-to-Entity Links

Properties with `type=entity` create direct edges:

- **Label**: Property name in CONST_CASE (e.g., `PASSPORT:holder` → `HOLDER`)
- Both source and target have `:Entity` label

## Edge Creation Rules

### Detecting Edge Entities

An entity is treated as an edge if:
- `schema.edge == True`
- Has both `schema.source_prop` and `schema.target_prop`

Common edge schemata: `Ownership`, `Directorship`, `Payment`, `Membership`, `Family`, etc.

### Edge Properties

From the source entity:
- **source_id**: Value from `source_prop`
- **target_id**: Value from `target_prop`
- **caption**: Entity caption
- **source**: Dataset provenance
- **sourceID**: Original referent IDs
- **Featured Properties**: All properties in `schema.featured` (except source/target props)

### Edge Labels

Edge labels are the schema name in CONST_CASE:
- `Ownership` → `:OWNERSHIP`
- `Directorship` → `:DIRECTORSHIP`
- `Payment` → `:PAYMENT`

### Multi-valued Sources/Targets

If either source or target property has multiple values, create a Cartesian product of edges (but skip self-loops).

## Special Handling

### Excluded Schemata

Certain entity types are skipped. This is specified in the YAML configuration file.

These are typically redundant with other representations.

### Orphan Node Cleanup

After loading, "orphan" value nodes (degree ≤ 1) are deleted for:
- `:identifier`
- `:email`
- `:phone`
- `:name`

This removes reified values that only connect to one entity (not useful for graph analysis).

## Database Constraints

Before loading, create unique constraints:

```cypher
CREATE CONSTRAINT entity_id IF NOT EXISTS
    FOR (n:Entity) REQUIRE (n.id) IS UNIQUE;

CREATE CONSTRAINT name_id IF NOT EXISTS
    FOR (n:name) REQUIRE (n.id) IS UNIQUE;

CREATE CONSTRAINT email_id IF NOT EXISTS
    FOR (n:email) REQUIRE (n.id) IS UNIQUE;

-- ... for each reified type
```

## Loading Order

1. **Create constraints** (for MERGE operations)
2. **Load all node entities** (entities where `schema.edge == False`)
3. **Load all reified value nodes and their edges**
4. **Load all edge entities** (entities where `schema.edge == True`)
5. **Cleanup orphan nodes** (optional)

## Implementation Differences

This project differs from `contrib/export.py` in the following ways:

### Old Approach (CSV-based)
- Generate CSV files for each label/edge type
- Create Cypher LOAD CSV script
- Requires HTTP server to serve CSVs
- Two-step process: export CSVs, then load into Neo4j

### New Approach (Direct)
- Stream entities directly from source files
- Use batched UNWIND operations for bulk insert
- Single-step process with progress logging
- No intermediate CSV files or HTTP server needed

## YAML Configuration Specification

This project uses a YAML configuration file to control the FTM-to-LPG transformation. This makes the conversion flexible and adaptable to different use cases.

### Configuration Structure

```yaml
# Database connection settings
db:
  url: "bolt://localhost:7687"
  username: "neo4j"
  password: "password"

# Node transformation rules
nodes:
  # Schema-specific node handling
  schemata:
    Security:
      ignore: true                    # Skip this entity type entirely
    Address:
      ignore: true                    # Don't create Address nodes
    Position:
      ignore: true
    Occupancy:
      ignore: true
    Person:
      label: "Human"                  # Override the default label
      properties:                     # Explicit property list (overrides defaults)
        - name
        - birthDate
        - deathDate
        - nationality

  # Property type reification rules
  types:
    name: true                        # Reify names into separate nodes
    address: true                     # Reify addresses into separate nodes
    identifier:
      reify: true
      caption: "raw"                  # Use raw value as caption
    country: false                    # Don't reify countries
    date: false                       # Don't reify dates
    email: true                       # Reify email addresses
    phone: true                       # Reify phone numbers
    url: true                         # Reify URLs

  # Topic-to-label mapping
  topics:
    labels:
      role.pep: "PEP"                    # Custom label for PEP topic
      gov.soe: "StateOwnedEnterprise"
    ignore:
      - mare.sts

# Edge transformation rules
edges:
  # Schema-specific edge handling
  schemata:
    Ownership:
      label: "OWNS"                   # Override default edge label
      properties:                     # Explicit property list
        - percentage
        - startDate
        - endDate
    Directorship:
      ignore: true                    # Don't create these edges

  # Property-based edge creation
  properties:
    "Sanction:entity":
      label: "SANCTIONED_ENTITY"      # Custom label for property-based edge
    "Passport:holder":
      label: "HOLDS_PASSPORT"
```

### Configuration Sections

#### Database (`db`)
Connection settings for the graph database (Neo4j/Memgraph).

#### Global Config (`config`)
- **join_values**: String separator for joining multi-valued properties (default: `";"`)

#### Nodes Configuration (`nodes`)

**Schemata Rules** (`nodes.schemata`):
- **ignore**: `true` to skip creating nodes for this schema
- **label**: Override the default node label (schema name)
- **properties**: Explicit list of properties to include (overrides defaults)

**Type Reification Rules** (`nodes.types`):
- **Boolean**: `true` to reify, `false` to inline only
- **Object**: Fine-grained control:
  - `reify`: Whether to create separate nodes
  - `caption`: How to format the caption (`"raw"`, `"formatted"`)

**Topic Mapping** (`nodes.topics`):
- **Boolean**: `true` uses default label conversion
- **Object**: Specify custom `label` for the topic

#### Edges Configuration (`edges`)

**Schemata Rules** (`edges.schemata`):
- **ignore**: `true` to skip creating edges for this relationship type
- **label**: Override the default edge label (schema name in CONST_CASE)
- **properties**: Explicit list of properties to include on edges

**Property-based Edges** (`edges.properties`):
For entity-reference properties (type `entity`):
- **label**: Custom edge label for this property reference
- Format: `"SchemaName:propertyName"`

### Default Behavior (No Config)

When no configuration is provided, or specific rules are missing:

**Nodes**:
- All non-edge entity schemata become nodes
- Labels are the schema name plus parent schemata
- Featured properties are inlined
- Property types `name`, `date`, `identifier`, `country` are inlined
- Property types `name`, `email`, `phone`, `identifier`, `url` are reified
- Topics use the built-in `TOPIC_ALIAS` mapping

**Edges**:
- All edge entity schemata become relationships
- Edge labels are schema names in CONST_CASE
- Featured properties (except source/target) are included
- Entity-reference properties create edges with property name as label

### Configuration Priorities

1. **Explicit schema rules** override type-based defaults
2. **Property lists** in schema config override featured/type defaults
3. **Custom labels** override automatic name conversions
4. **Ignore rules** take precedence over all other settings

### Implementation Notes & Design Decisions

#### Multi-Valued Properties

**Question**: Can Neo4j store multi-valued properties natively, or must we concatenate values?

**Answer**: Yes, Neo4j supports homogeneous arrays as property values:
- Property values can be primitive types OR arrays of a single primitive type
- Examples: `String[]`, `int[]`, `long[]`, etc.
- **Restriction**: Arrays must be homogeneous (all same type)
- **Restriction**: Arrays cannot contain `null` values
- Lists used in queries can be heterogeneous, but stored properties must be homogeneous

**Decision for this project**:
- Store multi-valued string properties as `String[]` arrays instead of concatenating
- This preserves individual values and enables better querying
- Example: `names: ["John Doe", "J. Doe"]` instead of `names: "John Doe; J. Doe"`

#### Multiple Label Assignment

**Question**: Can we apply all labels in one Cypher command, or do we need separate operations?

**Answer**: Yes, multiple labels can be set in a single operation:
- **CREATE**: `CREATE (n:Label1:Label2:Label3 {...})`
- **SET**: `SET n:Label1:Label2:Label3`
- **Dynamic**: `SET n:` can also accept a `LIST<STRING>` of label names
- Labels are separated by colons (`:`) or ampersands (`&`)

**Decision for this project**:
- Set all labels (schema, parent schemata, Entity, topics) in one CREATE/MERGE statement
- No need for separate CSV files per label as in the old approach
- Simpler code and better performance

#### Testability

**Question**: Can we make the converter testable by separating concerns?

**Answer**: Yes, we can separate the transformation logic from database operations:

**Architecture**:
1. **Read Layer** (`read.py`): Parse FTM entities from files
2. **Transform Layer** (`transform.py`): Convert entities to graph operations (nodes/edges)
3. **Write Layer**: Execute Cypher statements against database

**Testing Strategy**:
- Unit tests can validate transformation logic without database
- Integration tests can use in-memory or test database
- Transform layer returns structured data (dict/dataclass) representing nodes/edges
- Write layer consumes this structured data and executes Cypher

**Benefits**:
- Test transformation rules independently
- Verify label assignment, property mapping, reification logic
- Mock database for faster tests
- Easier to debug and validate behavior

#### Orphan Cleanup

**Question**: Should we implement orphan node cleanup?

**Decision**: Skip for now (as per PLAN.md)
- Orphan cleanup (removing nodes with degree ≤ 1) can be run as a post-processing step
- Not essential for core functionality
- Can be added as a separate CLI command later if needed
- Users can run manual Cypher queries for cleanup if desired:
  ```cypher
  MATCH (n:name) WHERE size((n)--()) <= 1
  DETACH DELETE n
  ```

### Open Questions

The proposal identifies areas still needing further design:

- **ID Generation**: Currently uses FTM entity IDs; could support custom ID schemes for integration - > use `registry.<type>.node_id`
- **Caption Formatting**: Currently uses entity caption; could support templates
- **Cross-dataset Integration**: How to merge/link with existing graphs in the database (handled in previous stage of ETL)
- **Property Filtering**: Should hidden/non-matchable properties be automatically excluded? - yes
- **Null Handling**: How to handle properties with empty/null values in arrays? - filter then out

## Example Transformations

### Person Entity
```json
{
  "id": "person-123",
  "schema": "Person",
  "properties": {
    "name": ["John Doe"],
    "birthDate": ["1980-01-01"],
    "nationality": ["us"],
    "passport": ["P123456"],
    "email": ["john@example.com"]
  },
  "datasets": ["sanctions"]
}
```

Becomes:
```
(:Person:LegalEntity:Entity {
  id: "person-123",
  caption: "John Doe",
  name: "John Doe",
  birthDate: "1980-01-01",
  nationality: "us",
  passport: "P123456",
  source: "sanctions"
})

(:Person)-[:HAS_NAME]->(:name {id: "name:john doe", caption: "John Doe"})
(:Person)-[:HAS_EMAIL]->(:email {id: "email:john@example.com", caption: "john@example.com"})
(:Person)-[:HAS_IDENTIFIER]->(:identifier {id: "identifier:P123456", caption: "P123456"})
```

### Ownership Entity
```json
{
  "id": "ownership-456",
  "schema": "Ownership",
  "properties": {
    "owner": ["person-123"],
    "asset": ["company-789"],
    "percentage": ["51"],
    "startDate": ["2020-01-01"]
  }
}
```

Becomes:
```
(:Entity {id: "person-123"})-[:OWNERSHIP {
  caption: "51%",
  percentage: "51",
  startDate: "2020-01-01",
  source: "..."
}]->(:Entity {id: "company-789"})
```

## Performance Considerations

- **Batch Size**: Use 10k-50k entities per transaction
- **UNWIND**: Batch inserts with UNWIND instead of individual statements
- **Constraints**: Create before loading to enable MERGE operations
- **Indexes**: Consider additional indexes on frequently queried properties
- **Memory**: Configure adequate heap for large datasets (8GB+ recommended)

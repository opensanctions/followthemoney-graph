# followthemoney-graph

The `followthemoney-graph` (`ftmg`) tool transforms and loads [FollowTheMoney](https://www.followthemoney.tech) entity data into a Neo4j property graph database. The tool provides flexible data transformation capabilities including filtering, reification of entity properties into graph nodes, and graph optimization.

## Features

- Load FollowTheMoney entities into Neo4j with configurable schema mappings
- Reify entity properties (names, addresses, identifiers, etc.) as graph nodes to reveal shared values
- Automatically create unique constraints and indexes for optimal query performance
- Prune single-reference reified nodes to optimize graph structure
- Support for custom label mappings and schema filtering
- Handles out-of-sequence data (nodes defined after edges that reference them)

## Installation

### Requirements

- Python 3.10 or higher
- Neo4j 5.0 or higher (running and accessible)

### Install from source

```bash
git clone https://github.com/opensanctions/followthemoney-graph.git
cd followthemoney-graph
pip install -e .
```

### Install for development

```bash
pip install -e ".[dev]"
```

This includes additional tools like `mypy`, `pytest`, and `coverage` for development.

## Configuration

Create a `config.yml` file to configure database connection and transformation settings:

```yaml
# Database connection settings
db:
  url: bolt://localhost:7687
  username: neo4j
  password: your_password

# Node configuration
nodes:
  # Schema-specific settings
  schemata:
    Position:
      ignore: true  # Skip this entity type
    Address:
      ignore: true  # Don't create Address entity nodes
    Person:
      label: "Human"  # Use custom label instead of "Person"

  # Property type reification
  types:
    address:
      reify: true  # Create separate nodes for address values
    identifier:
      reify: true  # Create separate nodes for identifiers
    phone:
      reify: true
    email:
      reify: true
    url:
      reify: true

  # Topic-based labeling
  topics:
    "sanction":
      label: "Sanctioned"
    "role.pep":
      label: "Politician"
    "poi":
      label: "PersonOfInterest"
    "gov.national":
      ignore: true  # Skip entities with this topic

# Edge configuration
edges:
  schemata:
    Occupancy:
      ignore: true  # Skip this relationship type
```

### Configuration Options

#### Database (`db`)

- `url`: Neo4j connection URL (bolt:// or neo4j://)
- `username`: Database username
- `password`: Database password

#### Nodes (`nodes`)

**Schemata Configuration** (`nodes.schemata`)

Configure how FollowTheMoney entity schemas are mapped:

- `ignore: true`: Skip entities of this schema type
- `label: "CustomLabel"`: Use a custom Neo4j label instead of the schema name

**Type Reification** (`nodes.types`)

Specify which property types should be reified as separate nodes:

- `reify: true`: Create a separate node for this property type
- When reified, properties like addresses or emails become nodes that can be shared between entities

**Topic Labels** (`nodes.topics`)

Map FollowTheMoney topics to Neo4j labels:

- `label: "CustomLabel"`: Apply this label to entities with the topic
- `ignore: true`: Skip entities with this topic

#### Edges (`edges`)

**Schemata Configuration** (`edges.schemata`)

Configure which relationship types to include:

- `ignore: true`: Skip relationships of this type

## Usage

The `ftmg` command-line tool provides several commands for managing your graph database:

### Check Configuration

Validate and display the expanded configuration:

```bash
ftmg check-config config.yml
```

This parses your configuration file and outputs the complete configuration including defaults.

### Load Data

Load FollowTheMoney entities from a JSON Lines file into Neo4j:

```bash
ftmg load config.yml --source entities.ftm.json
```

This command:
1. Creates unique constraints and indexes for all node types
2. Reads entities from the source file (JSON Lines format)
3. Transforms and loads them into Neo4j according to your configuration
4. Handles out-of-sequence data automatically

**Source file format**: Each line should contain a single FollowTheMoney entity as JSON.

### Prune Graph

Remove reified value nodes that are only referenced by a single entity:

```bash
ftmg prune config.yml
```

This optimization command:
- Identifies reified nodes (addresses, emails, identifiers, etc.)
- Counts unique entities referencing each reified node
- Deletes nodes referenced by fewer than 2 entities
- Reports the number of nodes pruned per type

**Why prune?** Reified nodes are most valuable when they reveal shared values between multiple entities. Single-reference reified nodes don't add structural value to the graph.

### Delete All Data

Completely wipe the database (use with caution):

```bash
ftmg trash config.yml
```

This command requires confirmation and will delete all nodes and relationships.

## Examples

### Basic Workflow

```bash
# 1. Validate your configuration
ftmg check-config config.yml

# 2. Load your data
ftmg load config.yml --source my-entities.ftm.json

# 3. Optimize the graph by removing single-reference reified nodes
ftmg prune config.yml
```

### Starting Fresh

```bash
# Clear the database
ftmg trash config.yml

# Load new data
ftmg load config.yml --source entities.ftm.json
```

## Graph Structure

### Entity Nodes

Entities are loaded as nodes with:
- Base label: `Entity`
- Schema label: e.g., `Person`, `Company`, `Asset`
- Topic labels: e.g., `Sanctioned`, `Politician` (if configured)
- Properties: All entity properties as node properties
- Special property: `id` (unique constraint enforced)

### Reified Value Nodes

When property types are marked for reification:
- Each unique value becomes a separate node
- Relationships connect entities to value nodes
- Value nodes can be shared between entities
- Labels: e.g., `address`, `identifier`, `email`
- Special property: `id` (unique constraint enforced)

### Relationships

Entity relationships are preserved as graph edges with:
- Relationship type based on the FollowTheMoney schema
- Properties from the relationship entity

## Development

### Running Tests

```bash
pytest
```

### Type Checking

```bash
mypy ftmg
```

### Code Coverage

```bash
pytest --cov=ftmg --cov-report=html
```

## Releasing

Releases to [PyPI](https://pypi.org/project/followthemoney-graph/) are published
automatically by the `build` GitHub Actions workflow when a version tag is pushed,
using PyPI Trusted Publishing (OIDC) — no API token is stored in the repository.

To cut a release:

```bash
bump2version patch   # or: minor / major — creates a commit and a vX.Y.Z tag
git push --follow-tags
```

The tag push runs the test/lint/type-check job, builds the wheel + sdist, attaches
a build-provenance attestation, and publishes to PyPI.

## Links

- [FollowTheMoney Documentation](https://followthemoney.tech/)
- [Neo4j Documentation](https://neo4j.com/docs/)
- [GitHub Repository](https://github.com/opensanctions/followthemoney-graph)
- [Issue Tracker](https://github.com/opensanctions/followthemoney-graph/issues)

## License

MIT License - see LICENSE file for details.

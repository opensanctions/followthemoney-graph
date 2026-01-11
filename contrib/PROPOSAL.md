Hey all!

We've seen a lot of interest recently for a more well-documented and flexible method ([current method](export.py)) for converting the OpenSanctions entity graph (nb: or the FollowTheMoney data model more broadly) into a Neo4J/Memgraph-compatible property graph.

Here's what we've identified as issues so far:
* Users want to select which entity types are going to be turned into nodes
* Users want to select which types of values linked to entities (eg. names, addresses, identifiers) will be turned into nodes. 
* We may also want to make the conversion of risk topics (e.g. PEP, sanctioned, etc.) into `labels` configurable.
* Similarly, the option to turn on/off particular edge types based on schemata (eg. Ownership, Directorship, etc.) or properties (eg. Passport:holder)

I've been thinking about turning this into a YAML configuration file that would define a mapping between the FtM/OS data and the property graph. Here's a sketch:

```yaml
source: "https://data.opensanctions.org/datasets/latest/default/entities.ftm.json"

config:
  join_values: ";"
  base_url: file:///where/neo4j/will/find/the/csvs

nodes:
  schemata:
    Security:
      ignore: true
    Address:
      ignore: true
    Person:
      label: Human
      properties:
        - name
        - birthDate
        - deathDate
  types:
    name: true
    address: true
    identifier:
      caption: raw
    country: false
    date: false
  topics:
    role.pep:
      label: PEP
    sanction: true
    sanction.linked: true

edges:
  schemata:
    Ownership:
      label: OWNS

  properties:
    "Sanction:target":
      label: TARGET
```

There's some things that this doesn't solve very well: 
* How to apply multi-valued properties to nodes/edges as string properties. 
* How to make the id generation for nodes configurable such that they can be made to collide with the IDs of another knowledge graph already present in the graph database (ie. how to make this snap into an existing, broader, in-house dataset).

The idea is to eventually make this executable as a Python tool:

```bash
pip install ftm-propgraph
ftm-propgraph spec.yml
```

I'm keen for any feedback: extra requirements, suggestions for a wholly different approach - etc... :)
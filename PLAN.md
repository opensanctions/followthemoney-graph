
* The current transformer appends to multiple CSV files - one per Neo4J label. I imagine that, as we write directly to the database, we can apply all labels in one Cypher command.
* Does Neo4J have any way to store/represent multi-valued properties? Can we avoid concatenating all the values for properties?
* Can we make the output of the converter testable by separating the database load step and evaluating the resulting nodes and edges in a test suite? 
* Let's skip orphan cleanup for now. 
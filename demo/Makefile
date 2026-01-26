
### Example 1: UK parliamentarians FtM mapping - one dataset
data/mps.json: | data
	ftm map --no-sign gb_mps.yml -o data/mps.json

data/mps.aggregated.json: data/mps.json
	ftm aggregate -i $< -o $@

data/mps.statements.csv: data/mps.json
	ftm statements -f csv -i $< -o $@

xref-mps: data/mps.aggregated.json
	nk xref --algorithm er-unstable data/mps.aggregated.json

dedupe-mps: data/mps.aggregated.json
	nk dedupe data/mps.aggregated.json

data/mps.resolved.json: data/mps.json
	nk apply $< -o $@

data/mps.merged.json: data/mps.resolved.json
	ftm aggregate -i $< -o $@


### Example 2: Multiple datasets and statements data format
data/de/aw_full.csv: data/de/aw_full.json
	ftm statements -d de_aw_full -f csv $< -o $@

data/de/aw_sidejobs.csv: data/de/aw_sidejobs.json
	ftm statements -d de_aw_sidejobs -f csv $< -o $@

data/de/aw_lobbykontakte.csv: data/de/aw_lobbykontakte.json
	ftm statements -d de_aw_lobbykontakte -f csv $< -o $@

data/de/parteispenden.csv: data/de/parteispenden.json
	ftm statements -d de_aw_parteispenden -f csv $< -o $@

data/de/aw_sponsoring.csv: data/de/aw_sponsoring.json
	ftm statements -d de_aw_sponsoring -f csv $< -o $@

data/de/lobbyregister.csv: data/de/lobbyregister.json
	ftm statements -d de_lobbyregister -f csv $< -o $@

data/de.statements.csv: data/de/aw_full.csv data/de/aw_sidejobs.csv data/de/aw_lobbykontakte.csv data/de/parteispenden.csv data/de/aw_sponsoring.csv data/de/lobbyregister.csv \
		data/os/de_bundestag.csv data/os/de_bundesrat.csv data/os/us_fara_filings.csv data/os/az_laundromat.csv
	qsv cat rows $^ | qsv search -v -s prop_type "^text$$" -o $@

data/de.resolved.csv: data/de.statements.csv
	nk apply-statements -i $< -o $@ -f csv

data/de.json: data/de.resolved.csv
	qsv sort -s canonical_id $< | ftm aggregate-statements -f csv -i - -o $@

xref-de: data/de.json
	nk xref -l 100000 --algorithm er-unstable -a 0.96 data/de.json
	rm -f data/de.resolved.csv data/de.json

dedupe-de: data/de.json
	nk dedupe data/de.json
	rm -f data/de.resolved.csv data/de.json




##################
### Example 3: Sanctions data aggregation and XRef
data/os:
	mkdir -p ./data/os

data/os/%.json: | data/os
	curl -s -R -o $@ https://data.opensanctions.org/datasets/latest/$*/entities.ftm.json

data/os/%.csv: data/os/%.json
	ftm statements -d $* -f csv $< -o $@

data/sanctions.csv: data/os/us_ofac_sdn.csv data/os/us_ofac_cons.csv data/os/eu_fsf.csv data/os/ch_seco_sanctions.csv data/os/gb_fcdo_sanctions.csv data/os/au_dfat_sanctions.csv data/os/ca_dfatd_sema_sanctions.csv
	qsv cat rows $^ -o $@

data/sanctions.filtered.csv: data/sanctions.csv
	qsv search -v -s schema '^(Sanction)$$' $< > $@

data/sanctions.resolved.csv: data/sanctions.filtered.csv
	nk apply-statements -i $< -o $@ -f csv

data/sanctions.sorted.csv: data/sanctions.resolved.csv
	qsv sort -u -s canonical_id $< -o $@

data/sanctions.json: data/sanctions.sorted.csv
	ftm aggregate-statements -f csv -i $< -o $@

xref-sanctions: data/sanctions.json
	nk xref -l 200000 --algorithm er-unstable -a 0.95 data/sanctions.json

data/large.csv: data/os/icij_offshoreleaks.csv data/os/az_laundromat.csv data/sanctions.csv
	qsv cat rows $^ -o $@

flush: 
	rm -rf nomenklatura.data
	nk prune

clear: flush
	rm -f nomenklatura.db data/mps.*

flush-de: 
	rm -rf nomenklatura.data
	rm -rf data/de.json data/de.resolved.csv

.PHONY: xref clear flush dedupe-mps xref-sanctions xref-mps
.PRECIOUS: %.json

data:
	mkdir -p ./data



## German political influence and lobbying data graph:
data/de: data
	mkdir -p ./data/de

data/de/aw_full.json: | data/de
	curl -s -R -o $@ https://data.ftm.store/de_abgeordnetenwatch_full/entities.ftm.json

data/de/aw_sidejobs.json: | data/de
	curl -s -R -o $@ https://data.ftm.store/de_abgeordnetenwatch_sidejobs/entities.ftm.json

data/de/aw_lobbykontakte.json: | data/de
	curl -s -R -o $@ https://data.ftm.store/de_abgeordnetenwatch_lobbykontakte/entities.ftm.json

data/de/parteispenden.json: | data/de
	curl -s -R -o $@ https://data.ftm.store/de_abgeordnetenwatch_parteispenden/entities.ftm.json

data/de/aw_sponsoring.json: | data/de
	curl -s -R -o $@ https://data.ftm.store/de_abgeordnetenwatch_sponsoring/entities.ftm.json

data/de/lobbyregister.json: | data/de
	curl -s -R -o $@ https://data.ftm.store/de_lobbyregister/entities.ftm.json
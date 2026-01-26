

data:
	mkdir -p ./data

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
	rm -rf data/xref-index
	nk prune

.PHONY: xref


## German political influence and lobbying data graph:
data/de: data
	mkdir -p ./data/de

data/de/aw_full.json: data/de
	curl -R -o ./data/de/aw_full.json https://data.ftm.store/de_abgeordnetenwatch_full/entities.ftm.json

data/de/aw_sidejobs.json: data/de
	curl -R -o ./data/de/aw_sidejobs.json https://data.ftm.store/de_abgeordnetenwatch_sidejobs/entities.ftm.json

data/de/aw_lobbykontakte.json: data/de
	curl -R -o ./data/de/aw_lobbykontakte.json https://data.ftm.store/de_abgeordnetenwatch_lobbykontakte/entities.ftm.json

data/de/parteispenden.json: data/de
	curl -R -o ./data/de/parteispenden.json https://data.ftm.store/de_abgeordnetenwatch_parteispenden/entities.ftm.json

data/de/aw_sponsoring.json: data/de
	curl -R -o ./data/de/aw_sponsoring.json https://data.ftm.store/de_abgeordnetenwatch_sponsoring/entities.ftm.json

data/de/lobbyregister.json: data/de
	curl -R -o ./data/de/lobbyregister.json https://data.ftm.store/de_lobbyregister/entities.ftm.json

data/de.json: data/de/aw_full.json data/de/aw_sidejobs.json data/de/aw_lobbykontakte.json data/de/parteispenden.json data/de/aw_sponsoring.json data/de/lobbyregister.json
	cat ./data/de/aw_full.json ./data/de/aw_sidejobs.json ./data/de/aw_lobbykontakte.json ./data/de/parteispenden.json ./data/de/aw_sponsoring.json ./data/de/lobbyregister.json > ./data/de.json

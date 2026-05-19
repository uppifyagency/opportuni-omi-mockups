.PHONY: serve open compute-modena compute-catanzaro compute-bologna compute-reggio-emilia compute-torino compute-firenze compute-napoli audit-all help

PORT ?= 8765

help:
	@echo "Targets:"
	@echo "  make serve                - avvia python3 http.server su porta $(PORT)"
	@echo "  make open                 - apre tutti i 21 mockup nel browser (richiede server attivo)"
	@echo "  make compute-<city>       - rigenera <city>-{signals,compass,volume-signals}.json"
	@echo "                              city ∈ {modena, catanzaro, bologna, reggio-emilia, torino, firenze, napoli}"
	@echo "  make audit-all            - esegue audit-math-proof.py su tutte le città"
	@echo ""
	@echo "Per replicare per una nuova provincia: vedi REPLICATE-FOR-OTHER-PROVINCE.md"

serve:
	@echo "Serving on http://localhost:$(PORT)/"
	@echo "Mockup Modena:        http://localhost:$(PORT)/mockups/investor-A-brief.html"
	@echo "Mockup Bologna:       http://localhost:$(PORT)/mockups/bologna-A-brief.html"
	@echo "Mockup Catanzaro:     http://localhost:$(PORT)/mockups/catanzaro-A-brief.html"
	@echo "Mockup Reggio Emilia: http://localhost:$(PORT)/mockups/reggio-emilia-A-brief.html"
	@echo "Mockup Torino:        http://localhost:$(PORT)/mockups/torino-A-brief.html"
	@echo "Mockup Firenze:       http://localhost:$(PORT)/mockups/firenze-A-brief.html"
	@echo "Mockup Napoli:        http://localhost:$(PORT)/mockups/napoli-A-brief.html"
	python3 -m http.server $(PORT)

open:
	@for city in investor bologna catanzaro reggio-emilia torino firenze napoli; do \
		open http://localhost:$(PORT)/mockups/$$city-A-brief.html; \
		open http://localhost:$(PORT)/mockups/$$city-B-heatmap.html; \
		open http://localhost:$(PORT)/mockups/$$city-C-compass.html; \
	done

compute-modena:
	python3 scripts/compute-modena-signals.py
	python3 scripts/compute-compass.py --city modena --codcom F257
	python3 scripts/compute-volume-signals.py

compute-catanzaro:
	python3 scripts/compute-catanzaro-signals.py
	python3 scripts/compute-catanzaro-compass.py
	python3 scripts/compute-volume-signals-catanzaro.py

compute-bologna:
	python3 scripts/compute-bologna-signals.py
	python3 scripts/compute-bologna-compass.py
	python3 scripts/compute-volume-signals-bologna.py

compute-reggio-emilia:
	python3 scripts/compute-reggio-emilia-signals.py
	python3 scripts/compute-reggio-emilia-compass.py
	python3 scripts/compute-volume-signals-reggio-emilia.py

compute-torino:
	python3 scripts/compute-torino-signals.py
	python3 scripts/compute-torino-compass.py

compute-firenze:
	python3 scripts/compute-firenze-signals.py
	python3 scripts/compute-firenze-compass.py
	python3 scripts/compute-volume-signals-firenze.py

compute-napoli:
	python3 scripts/compute-napoli-signals.py
	python3 scripts/compute-napoli-compass.py

audit-all:
	@for city in modena bologna catanzaro reggio-emilia torino firenze napoli; do \
		echo "=== Audit $$city ==="; \
		python3 scripts/audit-math-proof.py --city $$city || true; \
	done

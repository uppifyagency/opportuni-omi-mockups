.PHONY: serve open mockups-modena mockups-catanzaro compute-modena compute-catanzaro help

PORT ?= 8765

help:
	@echo "Targets:"
	@echo "  make serve              - avvia python3 http.server su porta $(PORT)"
	@echo "  make open               - apre i 6 mockup nel browser (richiede server attivo)"
	@echo "  make compute-modena     - rigenera modena-{signals,compass,volume-signals}.json"
	@echo "  make compute-catanzaro  - rigenera catanzaro-{signals,compass,volume-signals}.json"
	@echo ""
	@echo "Per replicare per una nuova provincia: vedi REPLICATE-FOR-OTHER-PROVINCE.md"

serve:
	@echo "Serving on http://localhost:$(PORT)/"
	@echo "Mockup Modena:    http://localhost:$(PORT)/mockups/investor-A-brief.html"
	@echo "Mockup Catanzaro: http://localhost:$(PORT)/mockups/catanzaro-A-brief.html"
	python3 -m http.server $(PORT)

open:
	@open http://localhost:$(PORT)/mockups/investor-A-brief.html
	@open http://localhost:$(PORT)/mockups/investor-B-heatmap.html
	@open http://localhost:$(PORT)/mockups/investor-C-compass.html
	@open http://localhost:$(PORT)/mockups/catanzaro-A-brief.html
	@open http://localhost:$(PORT)/mockups/catanzaro-B-heatmap.html
	@open http://localhost:$(PORT)/mockups/catanzaro-C-compass.html

compute-modena:
	python3 scripts/compute-modena-signals.py
	python3 scripts/compute-compass.py --city modena --codcom F257
	python3 scripts/compute-volume-signals.py

compute-catanzaro:
	python3 scripts/compute-catanzaro-signals.py
	python3 scripts/compute-catanzaro-compass.py
	python3 scripts/compute-volume-signals-catanzaro.py

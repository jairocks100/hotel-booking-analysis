What: enrich valid 2024 Goa/Manali bookings with Open-Meteo daily rain and maximum temperature.
Run: install ../requirements.txt, run python code/analysis.py from the root, then python project/weather_analyzer.py.
Outputs: city-date weather, validated booking merge, exposure tables, city-month contrasts, status and a four-sentence insight.
Design: batch one date range per city, merge many-to-one on city + check-in date, cache responses, retry timeouts.
Limitation: actual check-in weather and missing cancellation timestamps cannot establish weather causation.
Build status: live retrieval failed here; run with internet to complete the empirical insight; --self-test validates offline behavior.

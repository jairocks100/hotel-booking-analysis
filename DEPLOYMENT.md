# Hotel Weather web application

## Deployment status

The browser application and a GitHub Pages workflow are included in this repository. Committing the files is not proof of successful public deployment. The original Python analysis, SQL and command-line weather project are unchanged; their older README status statements refer to that original source upload.

## Enable public hosting

1. Open repository **Settings → Pages**.
2. Under **Build and deployment**, set **Source** to **GitHub Actions**.
3. Open **Actions → Deploy Hotel Weather to Pages → Run workflow**, select `main`, and run it. If the first automatic run failed before Pages activation, rerun it after enabling Pages.
4. Wait for a successful deploy and follow its environment link. This application uses the explicit entry point `hotel-weather.html`, not a root index document.
5. The expected application address after successful deployment is `https://jairocks100.github.io/hotel-booking-analysis/hotel-weather.html`. This is an expected address, not an assertion that hosting is currently active.

Only `site/` is included in the deployment artifact. No dataset, application email, PDF, customer-level output, local export or API credential is published. Existing Python code is not executed by Pages.

## Use the application

- Open the hosted HTML page.
- Choose the original booking workbook or a CSV with the same column names. Select the worksheet that contains booking records.
- Click **Fetch historical weather**. The app requests real Open-Meteo archive data for eligible Goa and Manali check-in dates in 2024, validates the response, and joins by city and date in Asia/Kolkata.
- Filter by city or weather exposure and optionally export the filtered records or the request audit.
- Click **Refresh current weather** for a separate current-conditions view. Current weather is never joined to old bookings.

For local use: `python -m http.server 8000 --directory site`, then open `http://localhost:8000/hotel-weather.html`.

## Verification performed before upload

A Chromium browser test against the actual local app and live APIs imported the original workbook locally: 12,000 rows, 11,460 valid rows, 926 eligible Goa/Manali 2024 bookings, and 926 complete historical-weather matches. Both current-weather API calls succeeded. Filtered CSV download succeeded, desktop and 375-pixel mobile layouts had no page-level overflow, and no browser page errors were recorded. JavaScript syntax checking and ESLint validation passed. These checks validate the local app, not public hosting; the private workbook and exported records are not committed.

## Scope and safeguards

- Required columns: `booking_id`, `property_city`, `booking_date`, `checkin_date`, `checkout_date`, `customer_signup_date`, `num_rooms`, `booking_status`.
- The importer is tailored to the supplied assessment schema, Goa/Manali spelling and 2024 check-ins. It is not a generic hotel-system connector.
- Workbook parsing and joins happen in browser memory. External font, spreadsheet-library and weather services receive ordinary network metadata; weather requests include coordinates and date ranges, not booking rows.
- Missing weather is unknown, never zero. Failed API requests remain visible and can be retried. Provider availability is not guaranteed.
- Exposure thresholds are analysis conventions: daily precipitation at least 20 mm, maximum temperature at least 35°C, or maximum temperature at most 5°C. They are not official warning definitions.
- Comparisons are descriptive associations, not causal cancellation estimates. City-grid and model-derived weather do not represent an individual hotel's measurements.
- CSV downloads include booking IDs, which may be sensitive, but omit names and contact details; formula-prefix characters are neutralized.
- No database, persistent user storage, backend, analytics or secret API keys are bundled.
- Open-Meteo free endpoints are subject to provider usage limits and non-commercial terms. Weather attribution links are included in the UI.

## Source integrity

SHA-256 of the tested app files:

```text
f42513199fd641ac94c6901e51ec67aec04d9406c9ec200c0ee106082ef3b20d  site/app.js
66c193050ca6d05ce5b804f3e9bc540ad6fccb81f2e1a249e143a0fc61d00734  site/hotel-weather.html
f13d440f8d0ceba87a18a59c67bb9030724f70cb99a6a9a435ddf873682c783e  site/style.css
```

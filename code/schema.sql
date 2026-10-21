-- SQLite 3.25+ dialect. DECIMAL declares intended precision; SQLite uses NUMERIC affinity.
-- Enforce production fixed-point precision using integer paise or a strict DECIMAL database.
PRAGMA foreign_keys = ON;
CREATE TABLE customers (
 customer_id INTEGER PRIMARY KEY,
 customer_name VARCHAR(120) NOT NULL,
 customer_segment VARCHAR(20) NOT NULL CHECK(customer_segment IN ('Individual','Group','Corporate')),
 customer_signup_date DATE NOT NULL,
 customer_home_city VARCHAR(80) NOT NULL,
 customer_loyalty_tier VARCHAR(20) NOT NULL CHECK(customer_loyalty_tier IN ('None','Silver','Gold','Platinum'))
);
CREATE TABLE properties (
 property_id INTEGER PRIMARY KEY,
 property_name VARCHAR(160) NOT NULL,
 property_city VARCHAR(80) NOT NULL,
 property_star_rating INTEGER NOT NULL CHECK(property_star_rating BETWEEN 1 AND 5),
 property_type VARCHAR(20) NOT NULL,
 property_total_rooms INTEGER NOT NULL CHECK(property_total_rooms > 0)
);
-- Do not assume property_name or (property_name,property_city) uniquely identifies a property.
CREATE TABLE bookings (
 booking_id INTEGER PRIMARY KEY,
 customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
 property_id INTEGER NOT NULL REFERENCES properties(property_id),
 booking_date DATE NOT NULL,
 checkin_date DATE NOT NULL,
 checkout_date DATE NOT NULL,
 room_type VARCHAR(30) NOT NULL,
 num_rooms INTEGER NOT NULL CHECK(num_rooms > 0), -- Footnote 3
 nights INTEGER NOT NULL CHECK(nights > 0),
 booking_channel VARCHAR(30) NOT NULL,
 adr DECIMAL(14,2) NOT NULL CHECK(adr >= 0),
 discount_amount DECIMAL(14,2) NOT NULL CHECK(discount_amount >= 0),
 coupon_code VARCHAR(40),
 total_amount DECIMAL(16,2) NOT NULL CHECK(total_amount >= 0),
 payment_method VARCHAR(30) NOT NULL,
 booking_status VARCHAR(20) NOT NULL CHECK(booking_status IN ('Completed','Cancelled','No-Show')),
 CHECK(checkout_date > checkin_date), -- Footnote 1; dates loaded in ISO format
 CHECK(checkin_date >= booking_date)
);
CREATE TABLE reviews (
 booking_id INTEGER PRIMARY KEY REFERENCES bookings(booking_id),
 review_rating DECIMAL(4,2) NOT NULL CHECK(review_rating BETWEEN 1 AND 5),
 review_date DATE
);
-- PKs/FKs are declared explicitly; every other column is neither a PK nor an FK.
-- Reviews store normalized 1-5 ratings: Corporate raw rating / 2; retain source in audit CSV.
-- Enforce signup-before-booking and review-status compatibility through ETL (cross-table checks).
CREATE INDEX idx_bookings_customer ON bookings(customer_id);
-- Speeds customer grouping/partition access in A-Q2; sorting by checkin_date may still be needed.

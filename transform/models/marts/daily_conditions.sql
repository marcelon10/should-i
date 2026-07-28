-- Mart: one row per location per day.
--
-- Deliberately *factual only* — no thresholds, no verdicts. Personal
-- preferences ("I won't bike above AQI 100") change often and belong in the
-- serving layer; if you bake them into the warehouse you have to rebuild
-- history every time you change your mind.

with hourly as (

    select * from {{ ref('stg_weather_hourly') }}

),

daylight as (

    select * from hourly
    where valid_hour between 7 and 20

),

commute as (

    select * from hourly
    where valid_hour in (8, 9, 17, 18)

)

select
    h.location_name,
    h.valid_date,

    count(*) as hours_observed,
    round(min(h.temperature_c), 1) as temp_min_c,
    round(max(h.temperature_c), 1) as temp_max_c,
    round(avg(h.temperature_c), 1) as temp_avg_c,
    max(h.precipitation_prob) as precip_prob_max,
    round(avg(h.wind_speed_kmh), 1) as wind_avg_kmh,
    round(max(h.wind_speed_kmh), 1) as wind_max_kmh,

    (
        select round(avg(d.temperature_c), 1) from daylight as d
        where
            d.location_name = h.location_name
            and d.valid_date = h.valid_date
    ) as daylight_temp_avg_c,
    (
        select max(d.precipitation_prob) from daylight as d
        where
            d.location_name = h.location_name
            and d.valid_date = h.valid_date
    ) as daylight_precip_prob_max,

    (
        select max(c.precipitation_prob) from commute as c
        where
            c.location_name = h.location_name
            and c.valid_date = h.valid_date
    ) as commute_precip_prob_max,
    (
        select round(max(c.wind_speed_kmh), 1) from commute as c
        where
            c.location_name = h.location_name
            and c.valid_date = h.valid_date
    ) as commute_wind_max_kmh,

    max(h.ingested_at) as last_ingested_at

from hourly as h
group by h.location_name, h.valid_date

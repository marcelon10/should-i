-- Staging: rename, cast, and lightly clean. No business logic here.
-- One row per (location, hour). Rows with an impossible temperature are
-- dropped rather than silently averaged into the marts.

with source as (

    select * from {{ source('raw', 'raw_weather_hourly') }}

),

renamed as (

    select
        location_name,
        valid_at,
        cast(valid_at as date) as valid_date,
        extract(hour from valid_at) as valid_hour,
        temperature_c,
        precipitation_prob,
        wind_speed_kmh,
        ingested_at,
        source_run_id
    from source

)

select *
from renamed
where temperature_c between -60 and 60

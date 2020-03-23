# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.


import pandas as pd


_queries = {
    "light_funnel_sampled_mau_city": '''
        WITH top_cities_t AS (
          SELECT
            COUNT(client_id) AS dau,
            CONCAT(country, ":", city) AS city
          FROM `moz-fx-data-shared-prod.telemetry.clients_daily`
          WHERE
            submission_date = "2020-03-01"
            AND city != "??"
            AND sample_id=67
          GROUP BY country, city
          ORDER BY dau DESC
          LIMIT 1000
        ),

        geo_t AS (
          SELECT
            client_id,
            city
          FROM (
            SELECT
              client_id,
              CONCAT(country, ":", cd_t.city) AS city,
              ROW_NUMBER() OVER(
                PARTITION BY client_id ORDER BY submission_date DESC
              ) AS rn
            FROM `moz-fx-data-shared-prod.telemetry.clients_daily` AS cd_t
            INNER JOIN (SELECT city FROM top_cities_t) AS top_cities_t
            ON CONCAT(cd_t.country, ":", cd_t.city) = top_cities_t.city
            WHERE
              submission_date > "1900-01-01"
              AND sample_id=67
          )
          WHERE rn = 1
        )

        SELECT
          submission_date AS date,
          COUNT(client_id) * 100 AS value,
          geo_t.city AS geo
        FROM (
            SELECT
              client_id,
              submission_date,
            FROM `moz-fx-data-shared-prod.telemetry.clients_daily`
            WHERE
              submission_date > "1900-01-01"
              AND sample_id=67
              AND attribution.content IS NOT NULL
          )

        INNER JOIN geo_t
        USING(client_id)
        GROUP BY city, submission_date
        '''
}


def get_raw_data(bq_client, bq_storage_client, metric):
    return bq_client.query(
        _queries[metric]
    ).result().to_dataframe(bqstorage_client=bq_storage_client)


def prepare_data(data, training_start, training_end):
    clean_data = {}
    clean_training_data = {}
    # Suppress any geoXdate with less than 5000 profiles as per minimum
    # aggregation standards for the policy this data will be released under.
    data = data[data.value >= 5000]
    for c in data.geo.unique():
        if (len(data.query("geo==@c") < 100):
            continue
        clean_data[c] = data.query("geo==@c").rename(
            columns={"date": "ds", "value": "y"}
        ).sort_values("ds")
        clean_data[c]['ds'] = pd.to_datetime(clean_data[c]['ds']).dt.date
        clean_data[c] = clean_data[c].set_index('ds')
        clean_training_data[c] = clean_data[c][
            training_start:training_end
        ].reset_index()
        clean_data[c] = clean_data[c].reset_index()
    return (clean_data, clean_training_data)

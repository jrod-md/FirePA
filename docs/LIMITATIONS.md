# Scientific and interpretive limitations

## Evidence boundary

FirePA is a descriptive pilot. Its scientific unit is a **provisional thermal
event**. The 611 units must not be described as confirmed fires, ignitions,
burn perimeters, or independent incidents.

## Thermal detections

NASA FIRMS records satellite-observed thermal anomalies. Detection depends on
sensor characteristics, overpass timing, atmosphere, cloud, pixel geometry,
and signal strength. A missing detection is not proof of no fire, and a
detection is not by itself proof of a wildfire.

## Grouping

`r1500_t06` is a frozen analytical convention, not ground truth. Connected
components may split prolonged documented activity when gaps exceed six hours
or may chain nearby observations. `possible_chain_merge` marks a review
condition; it is not a confirmed error or event class.

## Optical evidence

The optical cohort includes 28 observable cases and two `unobserved` cases.
`Unobserved` is not negative. NBR and dNBR are descriptive and may respond to
many land-surface and atmospheric conditions. FirePA provides no validated burn
scar, severity category, or causal attribution.

## Human evidence and modeling

Formal human observations equal zero. There is no ground truth, institutional
validation, defensible supervised target, trained predictive model, accuracy
estimate, or generalization claim. Automated calibration outputs are not human
observations and were not promoted to scientific labels.

## External references

The seven external documents describe two incidents, but they are relational
evidence only. The manual search was not exhaustive. Reported area and cause
claims are preserved per source and are not adjudicated by FirePA. Approximate
matching anchors were provided by the researcher.

For Los Picachos, zero official matches means only that no frozen event
satisfied the inclusive 5,000 m and temporal-overlap rule. The nearest
documented contemporary signal is 10,400.826 m away. The correct diagnosis is
`SPATIAL_THRESHOLD_MISS`; the result must not be translated into no fire, no
activity, no signal, or no event.

For Guacamaya, the six matches remain six separate provisional clusters. Five
gaps exceed six hours over 72.733 hours. `fragmentation_possible = true`
identifies a possible representation issue and does not authorize silently
merging the six units.

## Operational boundary

FirePA is not real-time and not operational. It does not provide alerts,
emergency response guidance, live monitoring, forecasting, severity estimates,
or validated decision support. The pilot is limited to Coclé and the inclusive
2025-01-01 to 2025-04-30 study window; no wider geographic or temporal
generalization is claimed.

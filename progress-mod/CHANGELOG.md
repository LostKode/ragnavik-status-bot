# Changelog

## 1.1.0

* Make the reporting endpoint, token file, token header, and server name configurable.
* Add independent switches for boss defeat and EpicMMO level reporting.
* Add configurable EpicMMO milestone intervals, defaulting to every 10 levels.
* Record the killing player and nearby participants for future boss defeats using in-game character names.
* Add configurable boss participant radius, defaulting to 100 meters.
* Establish quiet initial baselines and stable duplicate prevention across restarts.
* Keep normal creature kills silent.
* Default the public package to disabled with blank connection settings.
* Document receiver responsibilities, authentication, payload fields, Docker options, and Discord privacy guidance.

## 1.0.1

* Report world boss keys to the original Ragnavik status service.

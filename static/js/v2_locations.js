$(function () {
  // generate our gradient
  var colors = gradientFactory.generate({
    from: '#DDDDDD',
    to: primaryColor,
    stops: 7
  });

  // breaks for each gradient
  var breaks = [0, 5, 10, 25, 45, 65, 85];

  // default empty style
  var emptyStyle = function (feature) {
    return {
      fillColor: colors[1],
      weight: 1,
      opacity: 1,
      color: 'white',
      fillOpacity: 0.7
    };
  };

  var highlightStyle = {
    weight: 3,
    fillOpacity: 1
  };

  // our leaflet options
  var options = {
    // no user controlled zooming
    zoomControl: false,
    scrollWheelZoom: false,
    doubleClickZoom: false,
    boxZoom: false,

    // allow arbitrary scaling
    zoomSnap: 0,

    // remove leaflet attribution
    attributionControl: false,

    // don't allow dragging
    dragging: false
  };

  var initMap = function (id, geojson, url, districtZoom, wardZoom, wrapCoordinates) {
    var map = L.map(id, options);

    // constants
    var STATE_LEVEL = 1;
    var DISTRICT_LEVEL = 2;
    var WARD_LEVEL = 3;

    var boundaries = null;
    var countMap = null;

    var states = null;
    var stateResults = null;

    var topBoundary = null;

    var info = null;

    // this is our info box floating off in the top right
    info = new L.control();

    info.onAdd = function (map) {
      this._div = L.DomUtil.create('div', 'leaflet-info');
      var newParent = document.getElementById('map-info');
      var oldParent = document.getElementsByClassName('leaflet-control-container')[0];
      newParent.appendChild(oldParent);

      this.update();
      return this._div;
    };

    info.update = function (props) {
      if (props) {
        if (props.count != null) {
          if (props.count.unset != null) {
            var total = props.count.set + props.count.unset;
            this._div.innerHTML = "<div class='name'>" + props.name + "</div>" +
              "<div class='count'>" + props.count.set.toLocaleString() + " " + window.string_Responders + " // " + total.toLocaleString() + " " + window.string_Polled + "</div>";
          } else if (props.count.set != null) {
            this._div.innerHTML = "<div class='name'>" + props.name + "</div>" +
              "<div class='count'>" + props.count.set.toLocaleString() + " " + window.string_Reporters + "</div>";
          } else {
            this._div.innerHTML = "<div class='name'>" + props.name + "</div>";
          }
        } else {
          this._div.innerHTML = "";
        }
      } else {
        if (topBoundary != null) {
          if (topBoundary.unset != null) {
            var total = topBoundary.set + topBoundary.unset;
            this._div.innerHTML = "<div class='label'>" + window.string_TopRegion + ":</div><div class='name'>" + topBoundary.label + "</div>" +
              "<div class='count'>" + topBoundary.set.toLocaleString() + " " + window.string_Responders + " // " + total.toLocaleString() + " " + window.string_Polled + "</div>";
          } else if (topBoundary.set != null) {
            this._div.innerHTML = "<div class='label'>" + window.string_TopRegion + ":</div><div class='name'>" + topBoundary.label + "</div>" +
              "<div class='count'>" + topBoundary.set.toLocaleString() + " " + window.string_Reporters + "</div>";
          } else {
            this._div.innerHTML = "<div class='label'>" + window.string_TopRegion + ":</div><div class='name'>" + topBoundary.label + "</div>";
          }
        } else {
          this._div.innerHTML = "";
        }
      }
    };

    // rollover treatment
    var highlight = function (e) {
      var layer = e.target;
      var lvl = layer.feature.properties.level;
      if (!lvl ||
          (lvl === STATE_LEVEL && boundaries === states) ||
          ((lvl === DISTRICT_LEVEL || lvl === WARD_LEVEL) && boundaries !== states)) {
        layer.setStyle(highlightStyle);
        if (!L.Browser.ie && !L.Browser.opera) {
          layer.bringToFront();
        }
      }

      info.update(layer.feature.properties);
    };

    var clickFeature = function (e) {
      if (!districtZoom && !wardZoom) {
        highlight(e);
        return;
      }
      if (districtZoom && e.target.feature.properties.level === STATE_LEVEL) {
        map.removeLayer(states);
        loadBoundary(url, e.target.feature.properties, e.target);
      } else if (wardZoom && e.target.feature.properties.level === DISTRICT_LEVEL) {
        map.removeLayer(boundaries);
        loadBoundary(url, e.target.feature.properties, e.target);
      } else {
        resetBoundaries();
      }
    };

    // resets our color on mouseout
    var reset = function (e) {
      states.resetStyle(e.target);
      info.update();
    };

    // looks up the color for the passed in feature
    var countStyle = function (feature) {
      return {
        fillColor: feature.properties.color,
        weight: 1,
        opacity: 1,
        color: 'white',
        fillOpacity: 0.7
      };
    };

    var onEachFeature = function (feature, layer) {
      layer.on({
        mouseover: highlight,
        mouseout: reset,
        click: clickFeature
      });
    };

    var coordsToLatLng = function (coords) {
      var lon = coords[0];
      var lat = coords[1];
      if (lon < 0 && wrapCoordinates) {
        lon += 360;
      }
      return L.latLng(lat, lon);
    };

    var resetBoundaries = function () {
      map.removeLayer(boundaries);

      boundaries = states;
      countMap = stateResults;

      states.setStyle(countStyle);
      map.addLayer(states);
      map.fitBounds(states.getBounds());

      info.update();
    };

    var loadBoundary = function (url, boundary, target) {
      var boundaryId = boundary ? boundary.id : null;
      var boundaryLevel = boundary ? boundary.level : null;
      var segment;

      // load our actual data
      if (!boundary) {
        segment = { location: "State" };
      } else if (boundary && boundary.level === DISTRICT_LEVEL) {
        segment = { location: "Ward", parent: boundaryId };
      } else {
        segment = { location: "District", parent: boundaryId };
      }

      $.ajax({ url: url + '?segment=' + encodeURIComponent(JSON.stringify(segment)), dataType: "json" }).done(function (counts) {
        countMap = {};

        // figure out our max value
        var max = 0;
        for (var ci = 0; ci < counts.length; ci++) {
          var count = counts[ci];
          countMap[count.boundary] = count;
          if (count.set > max) {
            max = count.set;
            topBoundary = count;
          }
        }

        // and create mapping of threshold values to colors
        var colorSteps = [];
        for (var i = 0; i < colors.length; i++) {
          colorSteps[i] = {
            threshold: max * (breaks[i] / 100),
            color: colors[i]
          };
        }

        // we are displaying the districts of a state, load the geojson for it
        var boundaryUrl = '/boundaries/';
        if (boundaryId) {
          boundaryUrl += boundaryId + '/';
        }

        $.ajax({ url: boundaryUrl, dataType: "json" }).done(function (data) {
          // added to reset boundary when district has no wards
          if (data.features.length === 0) {
            resetBoundaries();
            return;
          }

          for (var fi = 0; fi < data.features.length; fi++) {
            var feature = data.features[fi];
            var props = feature.properties;
            var fcount = countMap[props.id].set;

            // merge our count values in
            props.count = countMap[props.id];

            props.color = colorSteps[colorSteps.length - 1].color;
            for (var si = 0; si < colorSteps.length; si++) {
              var step = colorSteps[si];
              if (fcount <= step.threshold) {
                props.color = step.color;
                break;
              }
            }
          }

          boundaries = L.geoJSON(data, {
            style: countStyle,
            onEachFeature: onEachFeature,
            coordsToLatLng: coordsToLatLng
          });
          boundaries.addTo(map);

          if (boundaryId) {
            states.resetStyle(target);
            map.removeLayer(states);
          } else {
            states = boundaries;
            stateResults = countMap;
          }

          $("#poll-map-placeholder").addClass('hidden');
          map.fitBounds(boundaries.getBounds());
          map.on('resize', function (e) {
            map.fitBounds(boundaries.getBounds());
          });
          info.update();
        });
      });
    };

    info.addTo(map);
    loadBoundary(url, null, null);
    return map;
  };

  if ($(".map").length > 0) {
    // fetch our top level states
    $.ajax({ url: '/boundaries/', dataType: "json" }).done(function (states) {
      // now that we have states, initialize each map
      $(".map").each(function () {
        var url = $(this).data("map-url");
        var id = $(this).attr("id");
        var districtZoom = $(this).data("district-zoom");
        var wardZoom = $(this).data("ward-zoom");
        var wrapCoordinates = $(this).data("wrap-coords");

        // no id? can't render, warn in console
        if (id === undefined) {
          console.log("missing map id, not rendering");
          return;
        }

        // no url? render empty map
        if (url === undefined) {
          console.log("missing map url, rendering empty");
          var map = L.map(id, options);
          var boundaries = L.geoJSON(states, { style: emptyStyle });
          boundaries.addTo(map);
          map.fitBounds(boundaries.getBounds());
          return;
        }

        var map = initMap(id, states, url, districtZoom, wardZoom, wrapCoordinates);
      });
    });
  }
});

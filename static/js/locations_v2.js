var initMap = function (id, geojson, question, districtZoom, wardZoom, colorsList) {
  if (colorsList == null) colorsList = [];
  var map = L.map(id, { scrollWheelZoom: false, zoomControl: false, touchZoom: false, trackResize: true, dragging: false }).setView([0, 0], 8);
  var STATE_LEVEL = 1;
  var DISTRICT_LEVEL = 2;
  var WARD_LEVEL = 3;

  var boundaries = null;
  var boundaryResults = null;

  var states = null;
  var stateResults = null;

  var info = null;

  var overallResults = null;
  var countryResults = null;

  var topBoundary = null;

  var topCategory = null;
  var otherCategory = null;
  var displayOthers = false;

  var mainLabelName = window.string_All;

  var colors = colorsList;

  if (!colors || colors.length !== 11) {
    colors = ['rgb(221, 221, 221)',
      'rgb(179, 207, 185)',
      'rgb(137, 194, 149)',
      'rgb(96, 181, 114)',
      'rgb(54, 168, 78)',
      'rgb(13, 155, 43)'];
  }

  var breaks = [0, 20, 40, 60, 80, 100];

  var visibleStyle = function (feature) {
    return {
      weight: 1,
      opacity: 1,
      color: 'white',
      fillOpacity: 1,
      fillColor: feature.properties.color
    };
  };

  var fadeStyle = function (feature) {
    return {
      weight: 1,
      opacity: 1,
      color: 'white',
      fillOpacity: 0.35,
      fillColor: "#2387ca"
    };
  };

  var hiddenStyle = function (feature) {
    return {
      fillOpacity: 0.0,
      opacity: 0.0
    };
  };

  var updateLegend = function (map, topBoundary) {
    var div = L.DomUtil.create("div", "info legend");

    var i = 0;

    while (i < breaks.length) {
      var idx = breaks.length - i - 1;
      var upper = breaks[idx];

      if (topBoundary) {
        div.innerHTML += "<i style=\"background:" + colors[idx] + "\"></i><br/>";
      }
      i++;
    }

    return div;
  };

  var calculateColor = function (percentage) {
    if (percentage < 0) {
      return 'rgb(200, 200, 200)';
    }

    for (var i = 0; i < breaks.length; i++) {
      if (breaks[i] >= percentage) {
        return colors[i];
      }
    }
  };

  var HIGHLIGHT_STYLE = {
    weight: 3,
    fillOpacity: 1
  };

  var highlightFeature = function (e) {
    var layer = e.target;
    var lvl = layer.feature.properties.level;
    if (!lvl ||
        (lvl === STATE_LEVEL && boundaries === states) ||
        ((lvl === DISTRICT_LEVEL || lvl === WARD_LEVEL) && boundaries !== states)) {
      layer.setStyle(HIGHLIGHT_STYLE);
      var html = "<div class='popup-region-name'>" + layer.feature.properties.name + "</div>" +
        "<div class='popup-responses-number'>" + layer.feature.properties.responses + " Responses</div>";
      L.popup().setLatLng(e.latlng).setContent(html).openOn(map);

      if (!L.Browser.ie && !L.Browser.opera) {
        layer.bringToFront();
      }

      info.update(layer.feature.properties);
    }
  };


  var resetBoundaries = function () {
    map.removeLayer(boundaries);

    boundaries = states;
    boundaryResults = stateResults;

    states.setStyle(visibleStyle);
    map.addLayer(states);
    map.fitBounds(states.getBounds(), { step: .25 });

    overallResults = countryResults;
    info.update();
  };

  var resetHighlight = function (e) {
    states.resetStyle(e.target);
    info.update();
  };

  var clickFeature = function (e) {
    if (districtZoom && e.target.feature.properties.level === STATE_LEVEL) {
      mainLabelName = e.target.feature.properties.name + " (" + window.string_State + ")";
      loadBoundary(e.target.feature.properties, e.target);
      scale.update(e.target.feature.properties.level);
    } else if (wardZoom && e.target.feature.properties.level === DISTRICT_LEVEL) {
      map.removeLayer(boundaries);
      mainLabelName = e.target.feature.properties.name + " (" + window.string_District + ")";
      loadBoundary(e.target.feature.properties, e.target);
      scale.update(e.target.feature.properties.level);
    } else {
      resetBoundaries();
      scale.update();
      mainLabelName = window.string_All;
    }
  };

  var loadBoundary = function (boundary, target) {
    var boundaryId = boundary ? boundary.id : null;
    var boundaryLevel = boundary ? boundary.level : null;
    var segment;

    // load our actual data
    if (!boundary) {
      segment = { location: "State" };
      overallResults = countryResults;
    } else if (boundary && boundary.level === DISTRICT_LEVEL) {
      segment = { location: "Ward", parent: boundaryId };
      overallResults = boundaryResults[boundaryId];
    } else {
      segment = { location: "District", parent: boundaryId };
      overallResults = boundaryResults[boundaryId];
    }

    $.ajax({ url: '/pollquestion/' + question + '/results/?segment=' + encodeURIComponent(JSON.stringify(segment)), dataType: "json" }).done(function (data) {
      var bi, b;
      // calculate the most common category if we haven't already
      if (!topBoundary) {
        var topPopulated = -1;

        for (bi = 0; bi < data.length; bi++) {
          b = data[bi];
          b.population = b.set;
          if (b.population > topPopulated) {
            topPopulated = b.population;
            topBoundary = b;
          }
        }

        // add our legend
        var legend = L.control({ position: "bottomright" });
        legend.onAdd = function (map) { return updateLegend(map, topBoundary); };
        legend.addTo(map);
      }

      boundaryResults = {};
      for (bi = 0; bi < data.length; bi++) {
        b = data[bi];
        if (topBoundary.population) {
          b.percentage = Math.round((100 * b.set) / topBoundary.population);
        } else {
          b.percentage = 0;
        }
        boundaryResults[b['boundary']] = b;
      }

      // update our summary total
      info.update();
      scale.update(boundaryLevel);

      // we are displaying the districts of a state, load the geojson for it
      var boundaryUrl = '/boundaries/';
      if (boundaryId) {
        boundaryUrl += boundaryId + '/';
      }

      $.ajax({ url: boundaryUrl, dataType: "json" }).done(function (data) {
        // added to reset boundary when district has no wards
        if (data.features.length === 0) {
          resetBoundaries();
          scale.update();
          return;
        }
        for (var fi = 0; fi < data.features.length; fi++) {
          var feature = data.features[fi];
          var result = boundaryResults[feature.properties.id];
          if (result) {
            feature.properties.scores = result.percentage;
            feature.properties.responses = result.set;
            feature.properties.color = calculateColor(result.percentage);
          } else {
            feature.properties.scores = 0;
            feature.properties.responses = 0;
            feature.properties.color = calculateColor(0);
          }

          feature.properties.borderColor = 'white';
        }

        boundaries = L.geoJson(data, { style: visibleStyle, onEachFeature: onEachFeature });
        boundaries.addTo(map);

        if (boundaryId) {
          states.resetStyle(target);
          map.removeLayer(states);
        } else {
          states = boundaries;
          stateResults = boundaryResults;
        }

        $("#" + id + "-placeholder").hide();
        map.fitBounds(boundaries.getBounds(), { step: .25 });

        map.on('resize', function (e) {
          map.fitBounds(boundaries.getBounds(), { step: .25 });
        });
      });
    });
  };


  var onEachFeature = function (feature, layer) {
    layer.on({
      mouseover: highlightFeature,
      mouseout: resetHighlight,
      click: clickFeature
    });
  };

  // turn off leaflet credits
  map.attributionControl.setPrefix('');

  var scale = L.control({ position: 'topright' });

  scale.onAdd = function (map) {
    this._div = L.DomUtil.create('div', 'scale');
    this.update();
    return this._div;
  };

  scale.update = function (level) {
    if (level == null) level = null;
    var html = "";

    var scaleClass = 'national';
    if (level && level === STATE_LEVEL) {
      scaleClass = 'state';
    } else if (level && level === DISTRICT_LEVEL) {
      scaleClass = 'district';
    }

    html = "<div class='scale " + scaleClass + "'>";
    html += "<div class='scale-map-circle-outer primary-border-color'></div>";
    html += "<div class='scale-map-circle-inner'></div>";
    html += "<div class='scale-map-hline primary-border-color'></div>";
    html += "<div class='scale-map-vline primary-border-color'></div>";
    html += "<div class='scale-map-vline-extended primary-border-color'></div>";
    html += "<div class='national-level primary-color'>" + window.string_All.toUpperCase() + "</div>";
    html += "<div class='state-level primary-color'>" + window.string_State.toUpperCase() + "</div>";
    html += "<div class='district-level primary-color'>" + window.string_District.toUpperCase() + "</div>";

    this._div.innerHTML = "";
  };


  // this is our info box floating off in the upper right
  info = L.control({ position: 'topleft' });

  info.onAdd = function (map) {
    this._div = L.DomUtil.create('div', 'info');
    this.update();
    return this._div;
  };

  info.update = function (props) {
    var html = "";

    var label = mainLabelName;
    var results = overallResults;

    if (props != null && props.id in boundaryResults) {
      label = props.name;
      results = boundaryResults[props.id];
      if (!results) {
        results = { set: 0, percentage: 0 };
      }
    }

    // wait until we have the totalRegistered to avoid division by zero
    if (topCategory) {
      html = "<div class='info'>";
      html += "<h2 class='admin-name'>" + label + "</h2>";

      html += "<div class='bottom-border info-title primary-color'>" + window.string_Participation_Level.toUpperCase() + "</div>";
      html += "<div><table><tr><td class='info-count'>" + window.intcomma(results.set) + "</td><td class='info-count'>" + window.intcomma(results.set + results.unset) + "</td></tr>";
      html += "<tr><td class='info-tiny'>" + window.string_Responders + "</td><td class='info-tiny'>" + window.string_Reporters_in + " " + label + "</td></tr></table></div>";

      html += "<div class='bottom-border info-title primary-color'>" + window.string_Results.toUpperCase() + "</div>";

      var percentage = results.percentage;
      var percentageTop, percentageOther;
      if (percentage < 0 || results.set === 0) {
        percentageTop = "--";
        percentageOther = "--";
      } else {
        percentageTop = percentage + "%";
        percentageOther = (100 - percentage) + "%";
      }

      html += "<div class='results'><table width='100%'>";

      html += "<tr class='row-top'><td class='info-percentage'>" + percentageTop + "</td>";
      html += "<td class='info-label'>" + topCategory + "</td></tr>";

      html += "<tr class='row-other'><td class='info-percentage other-color primary-border-color'>" + percentageOther + "</td>";
      html += "<td class='info-label primary-border-color'>" + otherCategory + "</td></tr>";

      html += "</table></div>";

      if (displayOthers && results.set > 0) {
        html += "<div class='other-details'>";
        html += "<div class='other-help'>";
        html += window.string_Other_answers;
        html += ":</div><table>";
        for (var lbl in results.others) {
          if (Object.prototype.hasOwnProperty.call(results.others, lbl)) {
            var count = results.others[lbl];
            var pct = Math.round((100 * count) / results.set);
            html += "<tr>";
            html += "<td class='detail-percentage'>" + pct + "%</td>";
            html += "<td class='detail-label'>" + lbl + "</td>";
            html += "</tr>";
          }
        }
        html += "</table></div>";
      }

      html += "</div>";
    }

    this._div.innerHTML = "";
  };


  info.addTo(map);
  scale.addTo(map);
  states = L.geoJson(geojson, { style: visibleStyle, onEachFeature: onEachFeature });
  states.addTo(map);

  loadBoundary(null, null);
  return map;
};

// global context for this guy
window.initMap = initMap;

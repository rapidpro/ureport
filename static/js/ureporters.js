var initMap = function (id, geojson, ajaxUrl, districtZoom, colorsList, wardZoom, reportersCount) {
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

  var totalRegistered = reportersCount;
  var topPopulated = 0;

  var topBoundary = null;

  var mainLabelName = window.string_All;
  var mainLabelRegistered = 0;

  var colors = colorsList;

  if (!colors) {
    colors = ['rgb(217,240,163)', 'rgb(173,221,142)', 'rgb(120,198,121)', 'rgb(65,171,93)', 'rgb(35,132,67)', 'rgb(0,104,55)'];
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
        div.innerHTML += "<i style=\"background:" + colors[idx] + "\"></i> " + upper + "% " + window.string_of + " " + window.string_the + " " + topBoundary.label + " " + window.string_total + "<br/>";
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
      mainLabelRegistered = totalRegistered;
    }
  };

  var loadBoundary = function (boundary, target) {
    var boundaryId = boundary ? boundary.id : null;
    var boundaryLevel = boundary ? boundary.level : null;
    var segment;

    // load our actual data
    if (!boundaryId) {
      segment = { location: "State" };
    } else if (boundary && boundary.level === DISTRICT_LEVEL) {
      segment = { location: "Ward", parent: boundaryId };
    } else {
      segment = { location: "District", parent: boundaryId };
    }

    $.ajax({ url: ajaxUrl + '?segment=' + encodeURIComponent(JSON.stringify(segment)), dataType: "json" }).done(function (data) {
      var bi, b;
      // calculate the most common category if we haven't already
      if (!topBoundary) {
        topPopulated = -1;

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

      mainLabelRegistered = 0;
      boundaryResults = {};
      for (bi = 0; bi < data.length; bi++) {
        b = data[bi];
        if (topBoundary.population) {
          b.percentage = Math.round((100 * b.set) / topBoundary.population);
        } else {
          b.percentage = 0;
        }
        boundaryResults[b['boundary']] = b;
        mainLabelRegistered += b.set;
        if (!boundaryId) {
          mainLabelRegistered = totalRegistered;
        }

        info.update();
        scale.update(boundaryLevel);
      }

      // we are displaying the districts of a state, load the geojson for it
      var boundaryUrl = '/boundaries/';
      if (boundaryId) {
        boundaryUrl += boundaryId + '/';
      }

      $.ajax({ url: boundaryUrl, dataType: "json" }).done(function (data) {
        if (data.features.length === 0) {
          resetBoundaries();
          scale.update();
          mainLabelName = window.string_All;
          return;
        }
        for (var fi = 0; fi < data.features.length; fi++) {
          var feature = data.features[fi];
          var result = boundaryResults[feature.properties.id];
          if (result) {
            feature.properties.scores = result.percentage;
            feature.properties.color = calculateColor(result.percentage);
          } else {
            feature.properties.scores = 0;
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

    this._div.innerHTML = html;
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

    html = "<div class='info'>";
    html += "<h2 class='admin-name'>" + mainLabelName + "</h2>";

    html += "<div class='bottom-border info-title primary-color'>" + window.string_Population.toUpperCase() + "</div>";
    html += "<div><table><tr><td class='info-count'>" + intcomma(mainLabelRegistered) + "</td></tr>";
    html += "<tr><td class='info-tiny'>" + window.string_Registered_in + " " + mainLabelName + "</td></tr></table></div>";

    if (props != null) {
      var result = boundaryResults[props.id];
      if (!result) {
        result = { set: 0, percentage: 0 };
      }

      html = "<div class='info'>";
      html += "<h2 class='admin-name'>" + props.name + "</h2>";

      html += "<div class='bottom-border info-title primary-color'>" + window.string_Population.toUpperCase() + "</div>";
      html += "<div><table><tr><td class='info-count'>" + intcomma(result.set) + "</td></tr>";
      html += "<tr><td class='info-tiny'>" + window.string_Registered_in + " " + props.name + "</td></tr></table></div>";

      html += "<div class='bottom-border hide-global-org info-title primary-color'>" + window.string_Density.toUpperCase() + "</div>";

      var percentage = result.percentage;
      var percentageTop;
      if (percentage < 0) {
        percentageTop = "--";
      } else {
        percentageTop = percentage + "%";
      }

      html += "<div class='info-percentage hide-global-org top-color'>" + percentageTop + "</div>";
      html += "<div class='info-tiny hide-global-org'>" + window.string_of + " " + window.string_the + " " + topBoundary.label + " total</div>";

      html += "</div>";
    }

    this._div.innerHTML = html;
  };


  info.addTo(map);
  scale.addTo(map);
  states = L.geoJson(geojson, { style: visibleStyle, onEachFeature: onEachFeature });
  states.addTo(map);

  loadBoundary(null, null);
};

// global context for this guy
window.initMap = initMap;

var initMap = function (id, geojson, question, region) {
  var map = L.map(id, { scrollWheelZoom: false, zoomControl: false, touchZoom: false, trackResize: true, dragging: false }).setView([0, 0], 8);

  var boundaries = null;
  var boundaryResults = null;

  var states = null;
  var stateResults = null;

  var info = null;

  var totalAnswered = 0;
  var totalRegistered = 0;

  var topCategory = null;


  var mainLabelName = gettext("All States");
  $.ajax({ url: "/boundaries/", dataType: "json" }).done(function (data) {
    for (var i = 0; i < data.features.length; i++) {
      var feature = data.features[i];
      if (feature.properties.id === region) {
        mainLabelName = feature.properties.name;
      }
    }
  });

  var mainLabelAnswered = 0;
  var mainLabelRegistered = 0;

  var colors = ['rgb(165,0,38)', 'rgb(215,48,39)', 'rgb(244,109,67)', 'rgb(253,174,97)', 'rgb(254,224,139)', 'rgb(255,255,191)', 'rgb(217,239,139)', 'rgb(166,217,106)', 'rgb(102,189,99)', 'rgb(26,152,80)', 'rgb(0,104,55)'];

  var breaks = [20, 30, 35, 40, 45, 55, 60, 65, 70, 80, 100];

  var visibleStyle = function (feature) {
    return {
      weight: 2,
      opacity: 1,
      color: 'white',
      fillOpacity: 1,
      fillColor: feature.properties.color
    };
  };

  var fadeStyle = function (feature) {
    return {
      weight: 2,
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

  var updateLegend = function (map, topCategory) {
    var div = L.DomUtil.create("div", "info legend");

    var i = 0;

    while (i < breaks.length) {
      var idx = breaks.length - i - 1;

      var lower = idx > 0 ? breaks[idx - 1] : 0;
      var upper = breaks[idx];

      if (lower < 50 && upper < 50) {
        var category = "Other";
        upper = 100 - upper;

        div.innerHTML += "<i style=\"background:" + colors[idx] + "\"></i> " + upper + "% " + category + "<br/>";
      } else if (lower > 50 && upper > 50) {
        var category = topCategory;

        div.innerHTML += "<i style=\"background:" + colors[idx] + "\"></i> " + lower + "% " + category + "<br/>";
      } else {
        div.innerHTML += "<i style=\"background:" + colors[i] + "\"></i>Even<br/>";
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
    weight: 6,
    fillOpacity: 1
  };

  var highlightFeature = function (e) {
    var layer = e.target;
    layer.setStyle(HIGHLIGHT_STYLE);

    if (!L.Browser.ie && !L.Browser.opera) {
      layer.bringToFront();
    }

    info.update(layer.feature.properties);
  };

  var resetBoundaries = function () {
    map.removeLayer(boundaries);

    boundaries = states;
    boundaryResults = stateResults;

    states.setStyle(visibleStyle);
    map.addLayer(states);
    map.fitBounds(states.getBounds(), { paddingTopLeft: [200, 0] });
  };

  var resetHighlight = function (e) {
    states.resetStyle(e.target);
    info.update();
  };


  var loadBoundary = function (boundaryId, target) {
    if (boundaryId == null) boundaryId = region;
    var segment;
    // load our actual data
    if (!boundaryId) {
      segment = { location: "State" };
    } else {
      segment = { location: "District", parent: boundaryId };
    }

    $.ajax({ url: '/pollquestion/' + question + '/results/?segment=' + encodeURIComponent(JSON.stringify(segment)), dataType: "json" }).done(function (data) {
      var bi, ci, b, c;
      // calculate the most common category if we haven't already
      if (!topCategory) {
        var categoryCounts = {};
        totalRegistered = 0;
        totalAnswered = 0;

        for (bi = 0; bi < data.length; bi++) {
          b = data[bi];
          for (ci = 0; ci < b['categories'].length; ci++) {
            c = b['categories'][ci];
            if (c.label in categoryCounts) {
              categoryCounts[c.label] += c.count;
            } else {
              categoryCounts[c.label] = c.count;
            }

            totalRegistered += b.set + b.unset;
            totalAnswered += b.set;
          }
        }

        var topCategoryCount = 0;
        for (var cat in categoryCounts) {
          if (Object.prototype.hasOwnProperty.call(categoryCounts, cat)) {
            if (categoryCounts[cat] > topCategoryCount) {
              topCategoryCount = categoryCounts[cat];
              topCategory = cat;
            }
          }
        }

        // add our legend
        var legend = L.control({ position: "bottomright" });
        legend.onAdd = function (map) { return updateLegend(map, topCategory); };
        legend.addTo(map);
      }

      // now calculate the percentage for each admin boundary
      mainLabelAnswered = 0;
      mainLabelRegistered = 0;
      boundaryResults = {};
      for (bi = 0; bi < data.length; bi++) {
        b = data[bi];
        // calculate the percentage of our top category vs the others
        b.percentage = -1;

        mainLabelAnswered += b.set;
        mainLabelRegistered += b.set + b.unset;
        info.update();
        for (ci = 0; ci < b['categories'].length; ci++) {
          c = b['categories'][ci];
          if (c.label === topCategory && b.set) {
            b.percentage = Math.round((100 * c.count) / b.set);
            break;
          }
        }

        boundaryResults[b['boundary']] = b;
      }

      // we are displaying the districts of a state, load the geojson for it
      var boundaryUrl = '/boundaries/';

      if (boundaryId) {
        boundaryUrl += boundaryId + '/';
      }

      $.ajax({ url: boundaryUrl, dataType: "json" }).done(function (data) {
        for (var fi = 0; fi < data.features.length; fi++) {
          var feature = data.features[fi];
          var result = boundaryResults[feature.properties.id];
          feature.properties.scores = result.percentage;
          feature.properties.color = calculateColor(result.percentage);
          feature.properties.borderColor = 'white';
        }

        boundaries = L.geoJson(data, { style: visibleStyle, onEachFeature: onEachFeature });
        boundaries.addTo(map);

        states = boundaries;
        stateResults = boundaryResults;

        map.fitBounds(boundaries.getBounds(), { paddingTopLeft: [200, 0] });
      });
    });
  };

  var onEachFeature = function (feature, layer) {
    layer.on({
      mouseover: highlightFeature,
      mouseout: resetHighlight
    });
  };

  // turn off leaflet credits
  map.attributionControl.setPrefix('');

  // this is our info box floating off in the upper right
  info = L.control({ position: 'topleft' });

  info.onAdd = function (map) {
    this._div = L.DomUtil.create('div', 'info');
    this.update();
    return this._div;
  };

  info.update = function (props) {
    var html = "";
    var percentage, percentageTop, percentageOther;

    // wait until we have the totalRegistered to avoid division by zero
    if (mainLabelRegistered) {
      html = "<div class='info'>";
      html += "<h2 class='admin-name'>" + mainLabelName + "</h2>";

      html += "<div class='top-border'>" + gettext("PARTICIPATION LEVEL") + "</div>";
      html += "<div><table><tr><td class='info-count'>" + mainLabelAnswered + "</td><td class='info-count'>" + window.intcomma(mainLabelRegistered) + "</td></tr>";
      html += "<tr><td class='info-tiny'>" + gettext("Responses") + "</td><td class='info-tiny'>" + gettext("Registered in") + " " + mainLabelName + "</td></tr></table></div>";

      html += "<div class='top-border'>" + gettext("RESPONSE RATE") + "</div>";

      percentage = Math.round((100 * mainLabelAnswered) / mainLabelRegistered);
      if (percentage < 0) {
        percentageTop = "--";
        percentageOther = "--";
      } else {
        percentageTop = percentage + " %";
        percentageOther = (100 - percentage) + " %";
      }

      html += "<div class='info-percentage top-color'>" + percentageTop + "</div>";
      html += "<div class='info-tiny'>" + topCategory + "</div>";

      html += "<div class='info-percentage other-color top-border' style='padding-top: 10px'>" + percentageOther + "</div>";
      html += "<div class='info-tiny'>" + gettext("Other") + "</div>";

      html += "</div>";
    }

    if (props != null) {
      var result = boundaryResults[props.id];

      html = "<div class='info'>";
      html += "<h2 class='admin-name'>" + props.name + "</h2>";

      html += "<div class='top-border'>" + gettext("PARTICIPATION LEVEL") + "</div>";
      html += "<div><table><tr><td class='info-count'>" + result.set + "</td><td class='info-count'>" + window.intcomma(result.set + result.unset) + "</td></tr>";
      html += "<tr><td class='info-tiny'>" + gettext("Responses") + "</td><td class='info-tiny'>" + gettext("Registered in") + " " + props.name + "</td></tr></table></div>";

      html += "<div class='top-border'>" + gettext("RESPONSE RATE") + "</div>";

      percentage = result.percentage;
      if (percentage < 0) {
        percentageTop = "--";
        percentageOther = "--";
      } else {
        percentageTop = percentage + " %";
        percentageOther = (100 - percentage) + " %";
      }

      html += "<div class='info-percentage top-color'>" + percentageTop + "</div>";
      html += "<div class='info-tiny'>" + topCategory + "</div>";

      html += "<div class='info-percentage other-color top-border' style='padding-top: 10px'>" + percentageOther + "</div>";
      html += "<div class='info-tiny'>" + gettext("Other") + "</div>";

      html += "</div>";
    }

    this._div.innerHTML = html;
  };


  info.addTo(map);
  states = L.geoJson(geojson, { style: visibleStyle, onEachFeature: onEachFeature });
  states.addTo(map);

  loadBoundary(region, null);
};

// global context for this guy
window.initMap = initMap;

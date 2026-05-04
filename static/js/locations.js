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

  var topCategory = null;
  var otherCategory = null;
  var displayOthers = false;

  var mainLabelName = window.string_All;

  var colors = colorsList;

  if (!colors || colors.length !== 11) {
    colors = ['rgb(165,0,38)', 'rgb(215,48,39)', 'rgb(244,109,67)', 'rgb(253,174,97)', 'rgb(254,224,139)', 'rgb(255,255,191)', 'rgb(217,239,139)', 'rgb(166,217,106)', 'rgb(102,189,99)', 'rgb(26,152,80)', 'rgb(0,104,55)'];
  }

  var breaks = [20, 30, 35, 40, 45, 55, 60, 65, 70, 80, 100];

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

  var updateLegend = function (map, topCategory) {
    var div = L.DomUtil.create("div", "info legend");

    // loop through our density intervals and generate a label with a colored square for each interval
    var i = 0;

    while (i < breaks.length) {
      var idx = breaks.length - i - 1;

      var lower = idx > 0 ? breaks[idx - 1] : 0;
      var upper = breaks[idx];

      if (lower < 50 && upper < 50) {
        var category = otherCategory;
        upper = 100 - upper;

        div.innerHTML += "<i style=\"background:" + colors[idx] + "\"></i> " + upper + "% " + category + "<br/>";
      } else if (lower > 50 && upper > 50) {
        var category = topCategory;

        div.innerHTML += "<i style=\"background:" + colors[idx] + "\"></i> " + lower + "% " + category + "<br/>";
      } else {
        div.innerHTML += "<i style=\"background:" + colors[i] + "\"></i>" + window.string_Even + "<br/>";
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
      var bi, ci, b, c, label;
      // calculate the most common category if we haven't already
      if (!topCategory) {
        var categoryCounts = {};

        for (bi = 0; bi < data.length; bi++) {
          b = data[bi];
          for (ci = 0; ci < b['categories'].length; ci++) {
            c = b['categories'][ci];
            if (c.label in categoryCounts) {
              categoryCounts[c.label] += c.count;
            } else {
              categoryCounts[c.label] = c.count;
            }
          }
        }

        var topCount = -1;
        var numCategories = 0;
        for (var cat in categoryCounts) {
          if (Object.prototype.hasOwnProperty.call(categoryCounts, cat)) {
            numCategories += 1;
            if (categoryCounts[cat] > topCount) {
              topCategory = cat;
              topCount = categoryCounts[cat];
            }
          }
        }

        // more than two categories? set our other category label to Other
        if (numCategories > 2) {
          otherCategory = window.string_Other;
          displayOthers = true;
        } else {
          // otherwise, set it to our other category
          displayOthers = false;
          for (var cat2 in categoryCounts) {
            if (Object.prototype.hasOwnProperty.call(categoryCounts, cat2)) {
              if (cat2 !== topCategory) {
                otherCategory = cat2;
                break;
              }
            }
          }
        }

        countryResults = { percentage: 0, totalTop: 0, totalOther: 0, set: 0, unset: 0, others: {} };
        for (bi = 0; bi < data.length; bi++) {
          b = data[bi];
          for (ci = 0; ci < b['categories'].length; ci++) {
            c = b['categories'][ci];
            if (c.label === topCategory) {
              countryResults.totalTop += c.count;
            } else {
              countryResults.totalOther += c.count;

              if (c.label in countryResults.others) {
                countryResults.others[c.label] += c.count;
              } else {
                countryResults.others[c.label] = c.count;
              }
            }
          }

          countryResults.set += b.set;
          countryResults.unset += b.unset;
        }

        if (countryResults.set + countryResults.unset > 0) {
          countryResults.percentage = Math.round((100 * countryResults.totalTop) / countryResults.set);
        }

        overallResults = countryResults;

        // add our legend
        var legend = L.control({ position: "bottomright" });
        legend.onAdd = function (map) { return updateLegend(map, topCategory); };
        legend.addTo(map);
      }

      // now calculate the percentage for each admin boundary
      boundaryResults = {};
      for (bi = 0; bi < data.length; bi++) {
        b = data[bi];
        // calculate the percentage of our top category vs the others
        b.percentage = -1;
        b.others = {};

        for (ci = 0; ci < b['categories'].length; ci++) {
          c = b['categories'][ci];
          if (c.label === topCategory && b.set) {
            b.totalTop = c.count;
            b.totalOther = b.set - c.count;
            b.percentage = Math.round((100 * c.count) / b.set);
          } else {
            b.others[c.label] = c.count;
          }
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

    this._div.innerHTML = html;
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

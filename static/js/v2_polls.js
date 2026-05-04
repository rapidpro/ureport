// wire in our segment pills
$(".segment-pill").click(function (e) {
  if (!$(this).hasClass("selected")) {
    // remove selection from sibling pills
    $(this).siblings().removeClass("selected");
    $(this).addClass("selected");

    var page = $(this).data("page");
    if (page === "opinions") {
      var questionID = $(this).data("question");
      var segment = $(this).data("segment");
      showChart(questionID, segment);
    }

    if (page === "engagement") {
      var metricSlug = $(this).data("metric-slug");
      var segmentType = $(this).data("segment-type");
      var timeFilter = $(this).data("time-filter");
      showEngagementChart(metricSlug, segmentType, timeFilter);
    }
  }

  e.stopPropagation();
  return false;
});

$(".state-pill").click(function () {
  var states = $(this).find(".state-dropdown");

  if (!$(states).hasClass("shown")) {
    $(states).addClass("shown");
    $(document).on("click.statePill", function () {
      $(states).removeClass("shown");
      $(document).off("click.statePill");
    });
  } else {
    $(states).removeClass("shown");
    $(document).off("click.statePill");
  }
  return false;
});

// state pill
$(".state-segment").click(function (e) {
  // count of currently selected
  var page = $(this).data("page");
  var count = $(this).siblings(".selected").length;

  if (!$(this).hasClass("selected")) {
    if (count < 5) {
      $(this).addClass("selected");
      if (page === "opinions") {
        var questionID = $(this).data("question");
        showChart(questionID, "state");
      }

      if (page === "engagement") {
        var metricSlug = $(this).data("metric-slug");
        var segmentType = $(this).data("segment-type");
        var timeFilter = $(this).data("time-filter");
        showEngagementChart(metricSlug, segmentType, timeFilter);
      }
    }
  } else {
    if (count > 0) {
      $(this).removeClass("selected");
      if (page === "opinions") {
        var questionID = $(this).data("question");
        showChart(questionID, "state");
      }

      if (page === "engagement") {
        var metricSlug = $(this).data("metric-slug");
        var segmentType = $(this).data("segment-type");
        var timeFilter = $(this).data("time-filter");
        showEngagementChart(metricSlug, segmentType, timeFilter);
      }
    }
  }

  e.stopPropagation();
  return false;
});

$(".tab-button-time-filter").click(function (e) {
  $(this).siblings().removeClass("selected");
  $(this).addClass("selected");
  var timeFilter = $(this).data("time-filter");
  $(".engagemment-content").addClass("hidden");
  $("#tab-content-block-" + timeFilter).removeClass("hidden");

  $("#tab-content-block-" + timeFilter).find(".selected.segment-pill").each(function (idx, el) {
    var page = $(this).data("page");
    if (page === "engagement") {
      var metricSlug = $(this).data("metric-slug");
      var segmentType = $(this).data("segment-type");
      var timeFilter = $(this).data("time-filter");
      showEngagementChart(metricSlug, segmentType, timeFilter);
    }
  });
  AOS.refresh();
  e.stopPropagation();
  return false;
});


// show the engagement chart with the passed in params
var showEngagementChart = function (metricSlug, segmentType, timeFilter) {
  var dataSlug = metricSlug + "-" + segmentType + "-" + timeFilter;
  var url = "/engagement_data/?results_params=" + encodeURIComponent(JSON.stringify({ "metric": metricSlug, "segment": segmentType, "filter": timeFilter }));
  var states = {};
  if (segmentType === "location") {
    $("#location-pill-" + dataSlug).find(".selected").each(function () {
      states[$(this).data("state")] = true;
    });
  }
  $('#engagement-graph-' + dataSlug).parent().parent().children().addClass("hidden");

  var colors = ['#98DFF9', '#FFC20E', '#FF7100', '#143E49', '#2653B9', '#e4002b'];

  if (segmentType === "gender") {
    colors = ['#98DFF9', '#FFC20E', '#FF7100'];
  }

  $.getJSON(url, function (results) {
    var total = 0;
    var series = [];

    var i = 0;
    for (var s = 0; s < results.length; s++) {
      var segment = results[s];
      var data = segment['data'];
      if (segmentType === "location" && !states[segment.osm_id]) {
        continue;
      }

      var cleanedData = [];
      for (var key in data) {
        if (Object.prototype.hasOwnProperty.call(data, key)) {
          cleanedData.push([Date.parse(key), data[key]]);
        }
      }
      cleanedData.sort(function (a, b) { return a[0] - b[0]; });

      series.push({
        name: segment.name,
        color: colors[i % colors.length],
        data: cleanedData
      });
      i++;
    }

    var chartType = "spline";
    if (segmentType === 'gender') {
      chartType = "column";
    }

    var pointFormat = '{point.x: %b %Y}: {point.y}';
    if (timeFilter != 12) {
      pointFormat = '{point.x: %e %b %Y}: {point.y}';
    }


    $('#engagement-graph-' + dataSlug).parent().removeClass("hidden");

    $("#engagement-graph-" + dataSlug).find('.chart-progress').hide();
    $("#engagement-graph-" + dataSlug).highcharts({
      chart: {
        type: chartType,
        backgroundColor: "#060e26",
        style: {
          fontFamily: "Noto Sans"
        }
      },
      credits: { enabled: false },
      legend: {
        enabled: true,
        verticalAlign: 'top',
        itemStyle: {
          color: "#DDD"
        }
      },
      title: { text: null },
      xAxis: {
        type: 'datetime',
        dateTimeLabelFormats: {
          month: '%b %Y',
          year: '%Y'
        },
        labels: {
          style: {
            color: "#DDD"
          }
        }
      },
      yAxis: {
        title: {
          text: null,
          style: {
            color: "#DDD"
          }
        },
        gridLineDashStyle: 'Dot',
        gridLineWidth: 0.3,
        min: 0,
        labels: {
          style: {
            color: "#DDD"
          }
        }
      },
      tooltip: {
        enabled: true,
        headerFormat: '<b>{series.name}</b><br>',
        pointFormat: pointFormat
      },
      plotOptions: {
        spline: {
          marker: {
            enabled: true
          }
        },
        column: {
          borderWidth: 0
        }
      },
      series: series
    });
  });
};

// shows the chart with the passed in question and segment
var showChart = function (questionID, segmentName) {
  var url = "/pollquestion/" + questionID + "/results/";
  var query = "";
  var states = {};

  if (segmentName === "gender") {
    query = "?segment=" + encodeURI(JSON.stringify({ gender: "Gender" }));
  } else if (segmentName === "age") {
    query = "?segment=" + encodeURI(JSON.stringify({ age: "Age" }));
  } else if (segmentName === "state") {
    $("#states-" + questionID).find(".selected").each(function () {
      states[$(this).data("state")] = true;
    });
    query = "?segment=" + encodeURI(JSON.stringify({ location: "State" }));
  }

  $.getJSON(url + query, function (results) {
    var total = 0;
    var s, c, segment, category;
    for (s = 0; s < results.length; s++) {
      segment = results[s];
      for (c = 0; c < segment.categories.length; c++) {
        total += segment.categories[c].count;
      }
    }

    var series = [];
    var categories = [];
    var data = [];

    var i = 0;
    for (s = 0; s < results.length; s++) {
      segment = results[s];
      categories = [];
      data = [];
      for (c = 0; c < segment.categories.length; c++) {
        category = segment.categories[c];
        categories.push(category.label);
        var cat_percentage = segment.set > 0 ? Math.round(category.count / segment.set * 100) : 0;

        data.push({
          name: category.label,
          y: cat_percentage,
          weight: cat_percentage,
          percent: cat_percentage
        });
      }

      // ignore states that aren't included
      if (segmentName === "state" && !states[segment.boundary]) {
        continue;
      }

      var color = orgColors[i % orgColors.length];
      i++;

      var barColor = $("#question-block-" + questionID).data("bar-color");
      if (barColor == null) {
        barColor = $("#chart-" + questionID).data("bar-color");
        if (barColor == null) {
          barColor = primaryColor;
        }
      }

      if (segmentName === "all") {
        color = barColor;
      }

      series.push({
        name: segment.label,
        color: color,
        categories: categories,
        data: data
      });
    }

    $("#chart-" + questionID).find('.chart-progress').hide();
    // open ended, use a cloud
    if (results[0].open_ended) {
      var wordCloudColors = gradientFactory.generate({
        from: '#DDDDDD',
        to: barColor,
        stops: 4
      });

      $("#chart-" + questionID).highcharts({
        chart: {
          marginTop: 0,
          marginBottom: 0,
          paddingTop: 0,
          paddingBottom: 0,
          style: {
            fontFamily: "Noto Sans"
          }
        },
        series: [{
          type: 'wordcloud',
          data: data,
          name: 'Occurrences'
        }],
        plotOptions: {
          wordcloud: {
            colors: wordCloudColors,
            minFontSize: 6,
            rotation: {
              orientations: 1
            }
          }
        },
        credits: { enabled: false },
        legend: { enabled: false },
        title: { text: null },
        yAxis: { visible: false },
        tooltip: { enabled: false }
      });
    }

    // no segments, bar chart
    else if (segmentName === "all") {
      $("#chart-" + questionID).highcharts({
        chart: {
          type: "bar",
          marginTop: 0,
          marginBottom: 0,
          style: {
            fontFamily: "Noto Sans"
          }
        },
        credits: { enabled: false },
        legend: { enabled: false },
        title: { text: null },
        yAxis: { visible: false },
        tooltip: { enabled: false },
        xAxis: {
          opposite: true,
          tickWidth: 0,
          lineColor: 'transparent',
          tickInterval: 1,
          labels: {
            enabled: true,
            style: {
              color: 'black',
              fontWeight: 'bold',
              fontSize: '1.25rem',
              textOutline: false
            },
            formatter: function () {
              return data[this.pos].percent + "%";
            }
          }
        },
        plotOptions: {
          bar: {
            maxPointWidth: 50
          },
          series: {
            color: 'rgb(95,180,225)',
            pointPadding: 0,
            groupPadding: 0.1,
            borderWidth: 0,

            dataLabels: {
              enabled: true,
              inside: true,
              align: "left",
              useHTML: true,
              crop: false,
              overflow: 'allow',
              padding: 10,
              style: {
                color: '#333',
                fontWeight: 'bold',
                fontSize: '0.75rem',
                textOutline: false,
                width: '180px',
                overflow: 'hidden'
              },
              formatter: function () {
                return this.point.name.toUpperCase();
              }
            }
          }
        },
        series: series
      });
    } else {
      // segments, lets do a column
      $("#chart-" + questionID).highcharts({
        chart: {
          type: "column",
          style: {
            fontFamily: "Noto Sans"
          }
        },
        credits: { enabled: false },
        legend: {
          enabled: true,
          verticalAlign: 'top'
        },
        title: { text: null },
        yAxis: { visible: false },
        tooltip: {
          enabled: true,
          pointFormat: '{series.name}: <b>{point.percent}%</b><br/>'
        },
        xAxis: {
          categories: categories,
          opposite: false,
          tickWidth: 0,
          lineColor: 'transparent',
          labels: {
            useHTML: true,
            align: 'center',
            autoRotation: false,
            enabled: true,
            style: {
              color: 'black',
              fontWeight: 'bold',
              fontSize: '.85rem',
              textOutline: false
            }
          }
        },
        plotOptions: {
          label: {
            maxPointWidth: 50
          },
          series: {
            color: 'rgb(95,180,225)',
            pointPadding: 0.1,
            groupPadding: 0.1,
            borderWidth: 0
          }
        },
        series: series
      });
    }
  });
};

$(function () {
  $(".poll-chart").each(function (idx, el) {
    var questionID = $(this).data("question");
    var questionSegment = $(this).data("segment");
    showChart(questionID, questionSegment);
  });
});

$(function () {
  $(".random-pill").each(function (idx, el) {
    var page = $(this).data("page");
    if (page === "engagement") {
      var pills = $(this).children('.segment-pill');
      var chosen = $(pills[Math.floor(Math.random() * pills.length)]);
      chosen.addClass("selected");
      var metricSlug = chosen.attr("data-metric-slug");
      var segmentType = chosen.attr("data-segment-type");
      var timeFilter = chosen.attr("data-time-filter");
      showEngagementChart(metricSlug, segmentType, timeFilter);
    }
  });
});

$(function () {
  var redrawChart = function (evt) {
    var page = $("#" + evt.detail.id).data("page");

    if (page === "engagement") {
      var graphDiv = $("#" + evt.detail.id).find(".engagement-graph").not(".hidden").find(".engagement-chart");
      var metricSlug = graphDiv.data("metric-slug");
      var segmentType = graphDiv.data("segment-type");
      var timeFilter = graphDiv.data("time-filter");
      showEngagementChart(metricSlug, segmentType, timeFilter);
    }

    if (page === "opinions") {
      var graphDiv = $("#" + evt.detail.id).find(".poll-chart");
      var questionID = graphDiv.data("question");
      var selectedPill = $("#" + evt.detail.id).find(".selected.segment-pill");
      var segment = selectedPill.data("segment");
      $("#chart-" + questionID).find('.chart-progress').show();
      showChart(questionID, segment);
    }
  };

  document.addEventListener('aos:in', redrawChart);
});

var showSchemeChart = function (id, data, barColor, labelColor) {
  // Note: labelPosition/labelSize/labelWeight referenced below are intentionally
  // resolved against globals if defined elsewhere, mirroring the original
  // CoffeeScript behavior.
  var colors = ['#2f7ed8', '#0d233a', '#8bbc21', '#910000', '#1aadce', '#492970', '#f28f43', '#77a1e5', '#c42525', '#a6c96a'];

  if (typeof labelPosition === 'undefined' || labelPosition == null) {
    var labelPosition = "bottom";
  }
  if (typeof labelSize === 'undefined' || labelSize == null) {
    var labelSize = 14;
  }
  if (typeof labelWeight === 'undefined' || labelWeight == null) {
    var labelWeight = 700;
  }

  var categories = [];
  for (var i = 0; i < data.length; i++) {
    categories.push(data[i].name);
  }

  $("#" + id).highcharts({
    chart: {
      type: 'bar',
      width: 450,
      backgroundColor: 'transparent',
      marginTop: labelPosition === "top" ? labelSize * 2.2 : 0,
      marginBottom: labelPosition === "bottom" ? labelSize * 2.2 : 0,
      style: {
        fontFamily: "Noto Sans"
      }
    },
    title: null,
    credits: { enabled: false },
    legend: { enabled: false },
    xAxis: {
      categories: categories,
      opposite: labelPosition === "top",
      lineColor: 'transparent',
      labels: {
        rotation: 0,
        style: {
          fontSize: labelSize,
          fontWeight: labelWeight,
          color: labelColor
        }
      }
    },
    yAxis: { visible: false },
    tooltip: { enabled: false },
    plotOptions: {
      series: {
        pointPadding: 0,
        groupPadding: 0.1,
        borderWidth: 0
      },
      bar: {
        color: barColor,
        pointPadding: 0,
        maxPointWidth: 35,
        dataLabels: {
          enabled: true,
          align: "left",
          style: {
            fontSize: ".75rem",
            textOutline: false,
            color: "white"
          },
          formatter: function () {
            return this.y + "%";
          }
        }
      }
    },
    series: [{
      data: data
    }]
  });
};


$(function () {
  $(".scheme-chart").each(function (idx, el) {
    var barColor = $(this).data("bar-color");
    var labelColor = $(this).data("label-color");
    var id = $(this).attr("id");
    var data = JSON.parse(document.getElementById($(this).data("stats")).textContent);
    showSchemeChart(id, data, barColor, labelColor);
  });
});

$(function () {
  var redrawAgeChart = function (evt) {
    var graphType = $("#" + evt.detail.id).data("graph-type");

    if (graphType === "scheme-chart") {
      var graphDiv = $("#" + evt.detail.id);

      var barColor = graphDiv.data("bar-color");
      var labelColor = graphDiv.data("label-color");
      var id = graphDiv.attr("id");
      var data = JSON.parse(document.getElementById(graphDiv.data("stats")).textContent);

      showSchemeChart(id, data, barColor, labelColor);
    }
  };

  document.addEventListener('aos:in', redrawAgeChart);
});

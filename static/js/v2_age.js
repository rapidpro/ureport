var showAgeChart = function (id, data, barColor, labelColor, labelPosition, labelSize, labelWeight) {
  if (labelPosition == null) {
    labelPosition = "bottom";
  }
  if (labelSize == null) {
    labelSize = 14;
  }
  if (labelWeight == null) {
    labelWeight = 700;
  }

  var categories = [];
  for (var i = 0; i < data.length; i++) {
    categories.push(data[i].name);
  }

  $("#" + id).highcharts({
    chart: {
      type: 'column',
      backgroundColor: 'transparent',
      marginTop: labelPosition === "top" ? labelSize * 2.2 : 0,
      marginBottom: labelPosition === "bottom" ? labelSize * 2.2 : 0,
      style: {
        fontFamily: "Noto Sans"
      }
    },
    credits: { enabled: false },
    legend: { enabled: false },
    title: { text: null },
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
      column: {
        color: barColor,
        pointPadding: 0,
        dataLabels: {
          enabled: true,
          verticalAlign: "bottom",
          style: {
            fontSize: ".75rem",
            textOutline: false,
            color: labelColor
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
  $(".age-chart").each(function (idx, el) {
    var barColor = $(this).data("bar-color");
    var labelColor = $(this).data("label-color");
    var labelPosition = $(this).data("label-position");
    var labelSize = $(this).data("label-size");
    var labelWeight = $(this).data("label-weight");
    var id = $(this).attr("id");
    var data = JSON.parse(document.getElementById($(this).data("stats")).textContent);
    showAgeChart(id, data, barColor, labelColor, labelPosition, labelSize, labelWeight);
  });
});

$(function () {
  var redrawAgeChart = function (evt) {
    var graphType = $("#" + evt.detail.id).data("graph-type");

    if (graphType === "age-chart") {
      var graphDiv = $("#" + evt.detail.id);

      var barColor = graphDiv.data("bar-color");
      var labelColor = graphDiv.data("label-color");
      var labelPosition = graphDiv.data("label-position");
      var labelSize = graphDiv.data("label-size");
      var labelWeight = graphDiv.data("label-weight");
      var id = graphDiv.attr("id");
      var data = JSON.parse(document.getElementById(graphDiv.data("stats")).textContent);

      showAgeChart(id, data, barColor, labelColor, labelPosition, labelSize, labelWeight);
    }
  };

  document.addEventListener('aos:in', redrawAgeChart);
});

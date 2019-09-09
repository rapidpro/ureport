$(->
  $(".age-chart").each(->
    barColor = $(this).data("bar-color")
    labelColor = $(this).data("label-color")
    id = $(this).attr("id")
    data = JSON.parse(document.getElementById($(this).data("stats")).textContent);

    categories = []
    i = 0
    while i < data.length
      categories.push(data[i].name)
      i++

    $("#" + id).highcharts({
      chart: {
        type: 'column'
        backgroundColor: 'transparent'
        marginTop: 0
        marginBottom: 28
        style: {
            fontFamily: "Montserrat"
        }
      }
      credits: { enabled: false }
      legend: { enabled: false }
      title: { text: null }
      xAxis: {
        categories: categories
        lineColor: 'transparent'
        labels: {
          rotation: 0
          style: {
            fontSize: '.75rem'
            fontWeight: 400
            color: labelColor
          }
        }
      }
      yAxis: { visible: false }
      tooltip: { enabled: false }
      plotOptions: {
        series: {
          pointPadding: 0
          groupPadding: 0.1
          borderWidth: 0
        }
        column: {
          color: barColor,
          pointPadding: 0
          dataLabels: {enabled: false}
        }
      }
      series: [{
        data: data
      }]
    })
  )
)
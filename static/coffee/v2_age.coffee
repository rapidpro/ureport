$(->
  $(".age-chart").each(->
    barColor = $(this).data("bar-color")
    labelColor = $(this).data("label-color")
    labelPosition = $(this).data("label-position")
    labelSize = $(this).data("label-size")

    if not labelPosition?
      labelPosition = "bottom"

    if not labelSize?
      labelSize = 14

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
        marginTop: if labelPosition == "top" then labelSize*2.2 else 0
        marginBottom: if labelPosition == "bottom" then labelSize*2.2 else 0
        style: {
            fontFamily: "Montserrat"
        }
      }
      credits: { enabled: false }
      legend: { enabled: false }
      title: { text: null }
      xAxis: {
        categories: categories
        opposite: if labelPosition == "top" then true else false
        lineColor: 'transparent'
        labels: {
          rotation: 0
          style: {
            fontSize: labelSize
            fontWeight: 700
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
          dataLabels: {
            enabled: true
            verticalAlign: "top"
            style: {
              fontSize: ".75rem"
              textOutline: false
              color: "black"
            }
            formatter: ->
              this.y + "%"
          }
        }
      }
      series: [{
        data: data
      }]
    })
  )
)
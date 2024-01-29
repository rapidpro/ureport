
showAgeChart = (id, data, barColor, labelColor, labelPosition, labelSize, labelWeight) ->
  if not labelPosition?
    labelPosition = "bottom"

  if not labelSize?
    labelSize = 14

  if not labelWeight?
    labelWeight = 700

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
          fontFamily: "Noto Sans"
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
          fontWeight: labelWeight
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
          verticalAlign: "bottom"
          style: {
            fontSize: ".75rem"
            textOutline: false
            color: labelColor
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


$(->
  $(".age-chart").each((idx, el) ->
    barColor = $(this).data("bar-color")
    labelColor = $(this).data("label-color")
    labelPosition = $(this).data("label-position")
    labelSize = $(this).data("label-size")
    labelWeight = $(this).data("label-weight")
    id = $(this).attr("id")
    data = JSON.parse(document.getElementById($(this).data("stats")).textContent);
    showAgeChart(id, data, barColor, labelColor, labelPosition, labelSize, labelWeight)
  )
)

$(->
  redrawAgeChart = (evt) ->
    graphType = $("#" + evt.detail.id).data("graph-type")
    
    if graphType == "age-chart"
      graphDiv = $("#" + evt.detail.id)

      barColor = graphDiv.data("bar-color")
      labelColor = graphDiv.data("label-color")
      labelPosition = graphDiv.data("label-position")
      labelSize = graphDiv.data("label-size")
      labelWeight = graphDiv.data("label-weight")
      id = graphDiv.attr("id")
      data = JSON.parse(document.getElementById(graphDiv.data("stats")).textContent);
  
      showAgeChart(id, data, barColor, labelColor, labelPosition, labelSize, labelWeight)
      

  document.addEventListener 'aos:in', redrawAgeChart
)
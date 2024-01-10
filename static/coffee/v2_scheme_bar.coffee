
showSchemeChart = (id, data, barColor, labelColor) ->
 
  colors = ['#2f7ed8', '#0d233a', '#8bbc21', '#910000', '#1aadce', '#492970', '#f28f43', '#77a1e5', '#c42525', '#a6c96a']

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
      type: 'bar'
      width: 450
      backgroundColor: 'transparent'
      marginTop: if labelPosition == "top" then labelSize*2.2 else 0
      marginBottom: if labelPosition == "bottom" then labelSize*2.2 else 0
      style: {
          fontFamily: "Noto Sans"
      }
    }
    title: null
    credits: { enabled: false }
    legend: { enabled: false }
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
      bar: {
        color: barColor,
        pointPadding: 0
        maxPointWidth: 35
        dataLabels: {
          enabled: true
          align: "left"
          style: {
            fontSize: ".75rem"
            textOutline: false
            color: "white"
          }
          formatter: ->
            this.y + "%"
        }
      }
    }

    series: [{
      data: data,
    }]
  })


$(->
  $(".scheme-chart").each((idx, el) ->
    barColor = $(this).data("bar-color")
    labelColor = $(this).data("label-color")
    id = $(this).attr("id")
    data = JSON.parse(document.getElementById($(this).data("stats")).textContent);
    showSchemeChart(id, data, barColor, labelColor)
  )
)

$(->
  redrawAgeChart = (evt) ->
    graphType = $("#" + evt.detail.id).data("graph-type")
    
    if graphType == "scheme-chart"
      graphDiv = $("#" + evt.detail.id)

      barColor = graphDiv.data("bar-color")
      labelColor = graphDiv.data("label-color")
      id = graphDiv.attr("id")
      data = JSON.parse(document.getElementById(graphDiv.data("stats")).textContent);
  
      showSchemeChart(id, data, barColor, labelColor)
      

  document.addEventListener 'aos:in', redrawAgeChart
)

showSchemeChart = (id, data) ->
 
  colors = ['#2f7ed8', '#0d233a', '#8bbc21', '#910000', '#1aadce', '#492970', '#f28f43', '#77a1e5', '#c42525', '#a6c96a']


  $("#" + id).highcharts({
    chart: {
      plotBackgroundColor: null
      plotBorderWidth: null
      plotShadow: false
      type: 'pie'
      width: 450
    }
    title: null
    credits: { enabled: false }
    tooltip: {
      pointFormat: '<b>{point.percentage:.1f}%</b> </br></br> {point.y}'
      useHTML: true
    }
    accessibility: {
      point: {
        valueSuffix: '%'
      }
    }
    plotOptions: {
      pie: {
        allowPointSelect: true,
        cursor: 'pointer',
        colors: colors,
        size: 200,
        dataLabels: {
          enabled: true,
          format: '<b>{point.name}</b>:</br> {point.percentage:.1f}%',
          color: 'white'
        }
      }
    }
    series: [{
      data: data,
    }]
  })


$(->
  $(".scheme-chart").each((idx, el) ->
    id = $(this).attr("id")
    data = JSON.parse(document.getElementById($(this).data("stats")).textContent);
    showSchemeChart(id, data)
  )
)

$(->
  redrawAgeChart = (evt) ->
    graphType = $("#" + evt.detail.id).data("graph-type")
    
    if graphType == "scheme-chart"
      graphDiv = $("#" + evt.detail.id)

      id = graphDiv.attr("id")
      data = JSON.parse(document.getElementById(graphDiv.data("stats")).textContent);
  
      showSchemeChart(id, data)
      

  document.addEventListener 'aos:in', redrawAgeChart
)
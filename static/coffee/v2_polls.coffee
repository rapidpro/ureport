# wire in our segment pills
$(".segment-pill").click((e) ->
  if not $(this).hasClass("selected")
    # remove selection from sibling pills
    $(this).siblings().removeClass("selected")
    $(this).addClass("selected")

    page = $(this).data("page")
    if page == "opinions"
      questionID = $(this).data("question")
      segment = $(this).data("segment")
      showChart(questionID, segment)

    if page == "engagement"

      metricSlug = $(this).data("metric-slug")
      segmentType = $(this).data("segment-type")
      timeFilter = $(this).data("time-filter")
      showEngagementChart(metricSlug, segmentType, timeFilter)

  e.stopPropagation()
  return false
)

$(".state-pill").click(->
  states = $(this).find(".state-dropdown")

  if not $(states).hasClass("shown")
    $(states).addClass("shown")
    $(document).click(->
      $(states).removeClass("shown")
      $(document).unbind("click")
    )
  else
    $(states).removeClass("shown")
    $(document).unbind("click")
  return false
)

# state pill
$(".state-segment").click((e) ->
  # count of currently selected
  page = $(this).data("page")
  count = $(this).siblings(".selected").length

  if not $(this).hasClass("selected")
    if count < 5
      $(this).addClass("selected")
      if page == "opinions"
        questionID = $(this).data("question")
        showChart(questionID, "state")

      if page == "engagement"
        metricSlug = $(this).data("metric-slug")
        segmentType = $(this).data("segment-type")
        timeFilter = $(this).data("time-filter")
        showEngagementChart(metricSlug, segmentType, timeFilter)

  else
    if count > 0
      $(this).removeClass("selected")
      if page == "opinions"
        questionID = $(this).data("question")
        showChart(questionID, "state")

      if page == "engagement"
        metricSlug = $(this).data("metric-slug")
        segmentType = $(this).data("segment-type")
        timeFilter = $(this).data("time-filter")
        showEngagementChart(metricSlug, segmentType, timeFilter)

  e.stopPropagation()
  return false
)

$(".tab-button-time-filter").click((e) ->
  $(this).siblings().removeClass("selected")
  $(this).addClass("selected")
  timeFilter = $(this).data("time-filter")
  $(".engagemment-content").addClass("hidden")
  $("#tab-content-block-" + timeFilter).removeClass("hidden")


  $("#tab-content-block-" + timeFilter).find(".selected.segment-pill").each((idx, el) ->
    page = $(this).data("page")
    if page == "engagement"
        metricSlug = $(this).data("metric-slug")
        segmentType = $(this).data("segment-type")
        timeFilter = $(this).data("time-filter")
        showEngagementChart(metricSlug, segmentType, timeFilter)
  )
  AOS.refresh()
  e.stopPropagation()
  return false
)


# show the engagement chart with the passed in params
showEngagementChart = (metricSlug, segmentType, timeFilter) ->
  dataSlug = metricSlug + "-" + segmentType + "-" + timeFilter
  url = "/engagement_data/?results_params=" + encodeURIComponent(JSON.stringify({"metric": metricSlug, "segment": segmentType, "filter": timeFilter}))
  states = {}
  if segmentType == "location"
    $("#location-pill-" + dataSlug).find(".selected").each(->
      states[$(this).data("state")] = true
    )
  $('#engagement-graph-' + dataSlug).parent().parent().children().addClass("hidden");

  colors = ['#98DFF9', '#FFC20E', '#FF7100', '#143E49', '#2653B9', '#e4002b']
  
  if segmentType == "gender"
    colors = ['#98DFF9', '#FFC20E', '#FF7100']

  $.getJSON(url, (results) ->
    total = 0
    series = []
    
    i = 0
    for segment in results
      data = segment['data']
      if segmentType == "location" and not states[segment.osm_id]
        continue

      cleanedData = []
      for key, value of data
        cleanedData.push([Date.parse(key), value])
      cleanedData.sort((a,b) ->  a[0] - b[0])

      series.push({
        name: segment.name,
        color: colors[i % colors.length]
        data: cleanedData
      })
      i++
    
    chartType = "spline"
    if segmentType == 'gender'
      chartType = "column"
    
    pointFormat = '{point.x: %b %Y}: {point.y}'
    if timeFilter != 12
      pointFormat = '{point.x: %e %b %Y}: {point.y}'


    $('#engagement-graph-' + dataSlug).parent().removeClass("hidden");
    
    $("#engagement-graph-" + dataSlug).find('.chart-progress').hide()
    $("#engagement-graph-" + dataSlug).highcharts({
        chart: {
          type: chartType
          backgroundColor: "#060e26"
          style: {
            fontFamily: "Noto Sans"
          }
        }
        credits: { enabled: false }
        legend: {
          enabled: true
          verticalAlign: 'top'
          itemStyle: {
            color: "#DDD"
          }
        }
        title: { text: null }
        xAxis: {
          type: 'datetime'
          dateTimeLabelFormats: {
            month: '%b %Y'
            year: '%Y'
          }
          labels: {
            style: {
              color: "#DDD"
            }
          }
        }
        yAxis: {
          title: {
            text: null
            style: {
              color: "#DDD"
            }
          }
          gridLineDashStyle: 'Dot'
          gridLineWidth: 0.3
          min: 0
          labels: {
            style: {
              color: "#DDD"
            }
          }
        }
        tooltip: {
          enabled: true
          headerFormat: '<b>{series.name}</b><br>'
          pointFormat: pointFormat
        }
        plotOptions: {
          spline: {
            marker: {
              enabled: true
            }
          },
          column: {
            borderWidth: 0
          }
        }
        series: series
      })
  )

# shows the chart with the passed in question and segment
showChart = (questionID, segmentName) ->
  url = "/pollquestion/" + questionID + "/results/"
  query = ""
  states = {}

  if segmentName == "gender"
    query = "?segment=" + encodeURI(JSON.stringify({gender: "Gender"}))
  else if segmentName == "age"
    query = "?segment=" + encodeURI(JSON.stringify({age: "Age"}))
  else if segmentName == "state"
    $("#states-" + questionID).find(".selected").each(->
      states[$(this).data("state")] = true
    )
    query = "?segment=" + encodeURI(JSON.stringify({location: "State"}))

  $.getJSON(url + query, (results) ->
    total = 0
    for segment in results
      for category in segment.categories
        total += category.count

    series = []
    categories = []

    i = 0
    for segment in results
      categories = []
      data = []
      for category in segment.categories
        categories.push(category.label)
        cat_percentage = if segment.set > 0 then Math.round(category.count / segment.set * 100) else 0

        data.push({
          name: category.label
          y: cat_percentage
          weight: cat_percentage
          percent: cat_percentage
        })

      # ignore states that aren't included
      if segmentName == "state" and not states[segment.boundary]
        continue
      
      color = orgColors[i % orgColors.length]
      i++

      barColor = $("#question-block-" + questionID).data("bar-color")
      if not barColor?
        barColor = $("#chart-" + questionID).data("bar-color")
        if not barColor?
          barColor = primaryColor

      if segmentName  == "all"
        color = barColor
      
      series.push({
        name: segment.label,
        color: color,
        categories: categories,
        data: data
      })

    $("#chart-" + questionID).find('.chart-progress').hide()
    # open ended, use a cloud
    if results[0].open_ended
      wordCloudColors = gradientFactory.generate({
        from : '#DDDDDD'
        to: barColor,
        stops: 4
      })

      $("#chart-" + questionID).highcharts({
        chart: {
          marginTop: 0
          marginBottom: 0
          paddingTop: 0
          paddingBottom: 0
          style: {
            fontFamily: "Noto Sans"
          }
        }
        series: [{
          type: 'wordcloud'
          data: data
          name: 'Occurrences'
        }]
        plotOptions: {
          wordcloud: {
            colors: wordCloudColors
            minFontSize: 6
            rotation: {
              orientations: 1
            }
          }
        }
        credits: { enabled: false }
        legend: { enabled: false }
        title: { text: null }
        yAxis: { visible: false }
        tooltip: { enabled: false }
      })

    # no segments, bar chart
    else if segmentName == "all"
      $("#chart-" + questionID).highcharts({
        chart: {
          type: "bar"
          marginTop: 0
          marginBottom: 0
          style: {
            fontFamily: "Noto Sans"
          }
        }
        credits: { enabled: false }
        legend: { enabled: false }
        title: { text: null }
        yAxis: { visible: false }
        tooltip: { enabled: false }
        xAxis: {
          opposite: true
          tickWidth: 0
          lineColor: 'transparent'
          tickInterval: 1
          labels: {
            enabled: true
            style: {
              color: 'black'
              fontWeight: 'bold'
              fontSize: '1.25rem'
              textOutline: false
            }
            formatter: ->
              return data[this.pos].percent + "%"
          }
        }
        plotOptions: {
          bar: {
            maxPointWidth: 50
          }
          series: {
            color: 'rgb(95,180,225)'
            pointPadding: 0
            groupPadding: 0.1
            borderWidth: 0

            dataLabels: {
              enabled: true
              inside: true
              align: "left"
              useHTML: true
              crop: false
              overflow: 'allow'
              padding: 10
              style: {
                color: '#333'
                fontWeight: 'bold'
                fontSize: '0.75rem'
                textOutline: false
                width: '180px'
                overflow: 'hidden'
              }
              formatter: ->
                return this.point.name.toUpperCase()
            }
          }
        }
        series: series
      })
    else
      # segments, lets do a column
      $("#chart-" + questionID).highcharts({
        chart: {
          type: "column"
          style: {
            fontFamily: "Noto Sans"
          }
        }
        credits: { enabled: false }
        legend: {
          enabled: true
          verticalAlign: 'top'
        }
        title: { text: null }
        yAxis: { visible: false }
        tooltip: {
          enabled: true
          pointFormat: '{series.name}: <b>{point.percent}%</b><br/>'
        }
        xAxis: {
          categories: categories
          opposite: false
          tickWidth: 0
          lineColor: 'transparent'
          labels: {
            useHTML: true
            align: 'center'
            autoRotation: false
            enabled: true
            style: {
              color: 'black'
              fontWeight: 'bold'
              fontSize: '.85rem'
              textOutline: false
            }
          }
        }
        plotOptions: {
          label: {
            maxPointWidth: 50
          }
          series: {
            color: 'rgb(95,180,225)'
            pointPadding: 0.1
            groupPadding: 0.1
            borderWidth: 0
          }
        }
        series: series
      })
  )

$(->
  $(".poll-chart").each((idx, el) ->
    questionID = $(this).data("question")
    questionSegment = $(this).data("segment")
    showChart(questionID, questionSegment)
  )
)

$(->
  $(".random-pill").each((idx, el) -> 
    page = $(this).data("page")
    if page == "engagement"
      chosen = $($(this).children('.segment-pill')[Math.floor(Math.random() * $(this).children('.segment-pill').length)])
      chosen.addClass("selected")
      metricSlug = chosen.attr("data-metric-slug")
      segmentType = chosen.attr("data-segment-type")
      timeFilter = chosen.attr("data-time-filter")
      showEngagementChart(metricSlug, segmentType, timeFilter)
  )
)

$(->
  redrawChart = (evt) ->
    page = $("#" + evt.detail.id).data("page")

    if page == "engagement"
      graphDiv = $("#" + evt.detail.id).find(".engagement-graph").not(".hidden").find(".engagement-chart")
      metricSlug = graphDiv.data("metric-slug")
      segmentType = graphDiv.data("segment-type")
      timeFilter = graphDiv.data("time-filter")
      showEngagementChart(metricSlug, segmentType, timeFilter)

    if page == "opinions"
      graphDiv = $("#" + evt.detail.id).find(".poll-chart")
      questionID = graphDiv.data("question")
      selectedPill = $("#" + evt.detail.id).find(".selected.segment-pill")
      segment = selectedPill.data("segment")
      $("#chart-" + questionID).find('.chart-progress').show()
      showChart(questionID, segment)

  document.addEventListener 'aos:in', redrawChart
)
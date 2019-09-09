# wire in our segment pills
$(".segment-pill").click(->
  # remove selection from sibling pills
  $(this).siblings().removeClass("selected")
  $(this).addClass("selected")

  questionID = $(this).data("question")
  segment = $(this).data("segment")
  showChart(questionID, segment)
  return false
)

# shows the chart with the passed in question and segment
showChart = (questionID, segmentName) ->
  url = "/pollquestion/" + questionID + "/results/"
  query = ""
  if segmentName == "gender"
    query = "?segment=" + encodeURI(JSON.stringify({gender: "Gender"}))
  else if segmentName == "age"
    query = "?segment=" + encodeURI(JSON.stringify({age: "Age"}))

  $.getJSON(url + query, (results) ->
    total = 0
    for segment in results
      for category in segment.categories
        total += category.count

    series = []
    for segment, i in results
      categories = []
      data = []
      for category in segment.categories
        categories.push(category.label)
        data.push({
          name: category.label
          y: category.count
          weight: category.count
          percent: if total > 0 then Math.round(category.count / total * 100) else 0
        })
      series.push({
        name: segment.label,
        color: orgColors[i % orgColors.length]
        categories: categories,
        data: data
      })

    # open ended, use a cloud
    if results[0].open_ended
      $("#chart-" + questionID).highcharts({
        series: [{
          type: 'wordcloud',
          data: data,
          name: 'Occurrences'
        }],
        plotOptions: {
          wordcloud: {
            colors: orgColors
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
            fontFamily: "Montserrat"
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
              padding: 10
              style: {
                color: '#333'
                fontWeight: 'bold'
                fontSize: '1.25rem'
                textOutline: false
              }
              formatter: ->
                return this.point.name.toUpperCase()
            }
          }
        }
        # series: series
        series: series
      })
    else
      # segments, lets do a column
      $("#chart-" + questionID).highcharts({
        chart: {
          type: "column"
          style: {
            fontFamily: "Montserrat"
          }
        }
        credits: { enabled: false }
        legend: {
          enabled: true
          verticalAlign: 'top'
        }
        title: { text: null }
        yAxis: { visible: false }
        tooltip: { enabled: true }
        xAxis: {
          categories: series[0].categories
          opposite: false
          tickWidth: 0
          lineColor: 'transparent'
          labels: {
            enabled: true
            style: {
              color: 'black'
              fontWeight: 'bold'
              fontSize: '1.25rem'
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
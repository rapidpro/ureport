initMap = (id, geojson, question, districtLabel) ->
  map = L.map(id, {scrollWheelZoom: false, zoomControl: false, touchZoom: false, trackResize: true,  dragging: false}).setView([0, 0], 8)
  STATE_LEVEL = 1
  DISTRICT_LEVEL = 2
  WARD_LEVEL = 3

  allowDistrictZoom = districtLabel.trim() != ''

  boundaries = null
  boundaryResults = null

  states = null
  stateResults = null

  info = null

  overallResults = null
  countryResults = null

  topCategory = null
  otherCategory = null
  displayOthers = false

  mainLabelName = window.string_All

  colors = ['rgb(165,0,38)','rgb(215,48,39)','rgb(244,109,67)','rgb(253,174,97)','rgb(254,224,139)','rgb(255,255,191)','rgb(217,239,139)','rgb(166,217,106)','rgb(102,189,99)','rgb(26,152,80)','rgb(0,104,55)']

  breaks = [20, 30, 35, 40, 45, 55, 60, 65, 70, 80, 100]

  visibleStyle = (feature) ->
    return {
      weight: 1
      opacity: 1
      color: 'white'
      fillOpacity: 1
      fillColor: feature.properties.color
    }

  fadeStyle = (feature) ->
    return {
      weight: 1
      opacity: 1
      color: 'white'
      fillOpacity: 0.35
      fillColor: "#2387ca"
    }

  hiddenStyle = (feature) ->
    return {
      fillOpacity: 0.0
      opacity: 0.0
    }

  updateLegend = (map, topCategory) ->
    div = L.DomUtil.create("div", "info legend")

    # loop through our density intervals and generate a label with a colored square for each interval
    i = 0

    while i < breaks.length
      idx = breaks.length - i - 1

      lower = if idx > 0 then breaks[idx-1] else 0
      upper = breaks[idx]

      if lower < 50 and upper < 50
        category = otherCategory
        upper = 100 - upper

        div.innerHTML += "<i style=\"background:" + colors[idx] + "\"></i> " + upper + "% " + category + "<br/>"

      else if lower > 50 and upper > 50
        category = topCategory

        div.innerHTML += "<i style=\"background:" + colors[idx] + "\"></i> " + lower + "% " + category + "<br/>"
      else
        div.innerHTML += "<i style=\"background:" + colors[i] + "\"></i>" + window.string_Even + "<br/>"
      i++

    return div

  calculateColor = (percentage) ->
    if percentage < 0
      return 'rgb(200, 200, 200)'

    for cutoff, i in breaks
      if cutoff >= percentage
        return colors[i]

  HIGHLIGHT_STYLE =
    weight: 3
    fillOpacity: 1

  highlightFeature = (e) ->
    layer = e.target
    if (
      not layer.feature.properties.level or
      layer.feature.properties.level == STATE_LEVEL and
      boundaries is states or
      layer.feature.properties.level in [DISTRICT_LEVEL, WARD_LEVEL] and
      boundaries isnt states
    )
      layer.setStyle(HIGHLIGHT_STYLE)

      if (!L.Browser.ie && !L.Browser.opera)
        layer.bringToFront()

      info.update(layer.feature.properties)

  resetBoundaries = ->
    map.removeLayer(boundaries)

    boundaries = states
    boundaryResults = stateResults

    states.setStyle(visibleStyle)
    map.addLayer(states)
    map.fitBounds(states.getBounds(), {step: .25})

    overallResults = countryResults
    info.update()

  resetHighlight = (e) ->
    states.resetStyle(e.target)
    info.update()

  clickFeature = (e) ->
    if e.target.feature.properties.level in [STATE_LEVEL, DISTRICT_LEVEL] and allowDistrictZoom
      map.removeLayer(boundaries)
      mainLabelName = e.target.feature.properties.name + " (" + window.string_State + ")"
      if e.target.feature.properties.level == DISTRICT_LEVEL
        mainLabelName = e.target.feature.properties.name + " (" + window.string_District + ")"
      loadBoundary(e.target.feature.properties, e.target)
      scale.update(e.target.feature.properties.level)
    else
      resetBoundaries()
      scale.update()
      mainLabelName = window.string_All

  loadBoundary = (boundary, target) ->
    boundaryId = if boundary then boundary.id else null
    boundaryLevel = if boundary then boundary.level else null
    # load our actual data
    if not boundary
      segment = {location:"State"}
      overallResults = countryResults
    else if boundary and boundary.level == DISTRICT_LEVEL
      segment = {location:"Ward", parent:boundaryId}
      overallResults = boundaryResults[boundaryId]
    else
      segment = {location:"District", parent:boundaryId}
      overallResults = boundaryResults[boundaryId]

    $.ajax({url:'/pollquestion/' + question + '/results/?segment=' + encodeURIComponent(JSON.stringify(segment)), dataType: "json"}).done (data) ->
      # calculate the most common category if we haven't already
      data = data || []
      if data.length == 0
        resetBoundaries()
        scale.update()
        mainLabelName = window.string_All
        return
      if not topCategory
        categoryCounts = {}

        for boundary in data
          for category in boundary['categories']
            if category.label of categoryCounts
              categoryCounts[category.label] += category.count
            else
              categoryCounts[category.label] = category.count

        topCount = -1
        numCategories = 0
        for category, count of categoryCounts
          numCategories += 1
          if count > topCount
            topCategory = category
            topCount = count

        # more than two categories? set our other category label to Other
        if numCategories > 2
          otherCategory = window.string_Other
          displayOthers = true
        else
          # otherwise, set it to our other category
          displayOthers = false
          for category, count of categoryCounts
            if category != topCategory
              otherCategory = category
              break

        countryResults = {percentage: 0, totalTop:0, totalOther:0, set:0, unset:0, others: {}}
        for boundary in data
          for category in boundary['categories']
            if category.label == topCategory
              countryResults.totalTop += category.count
            else
              countryResults.totalOther += category.count

              if category.label of countryResults.others
                countryResults.others[category.label] += category.count
              else
                countryResults.others[category.label] = category.count

          countryResults.set += boundary.set
          countryResults.unset += boundary.unset

        if countryResults.set + countryResults.unset > 0
          countryResults.percentage = Math.round((100 * countryResults.totalTop) / countryResults.set)

        overallResults = countryResults

        # add our legend
        legend = L.control(position: "bottomright")
        legend.onAdd = (map) -> updateLegend(map, topCategory)
        legend.addTo(map)

      # now calculate the percentage for each admin boundary
      boundaryResults = {}
      for boundary in data
        # calculate the percentage of our top category vs the others
        boundary.percentage = -1
        boundary.others = {}

        for category in boundary['categories']
          if category.label == topCategory and boundary.set
            boundary.totalTop = category.count
            boundary.totalOther = boundary.set - category.count
            boundary.percentage = Math.round((100 * category.count) / boundary.set)
          else
            boundary.others[category.label] = category.count

        boundaryResults[boundary['boundary']] = boundary

      # update our summary total
      info.update()
      scale.update(boundaryLevel)

      # we are displaying the districts of a state, load the geojson for it
      boundaryUrl = '/boundaries/'
      if boundaryId
        boundaryUrl += boundaryId + '/'

      $.ajax({url:boundaryUrl, dataType: "json"}).done (data) ->
        for feature in data.features
          result = boundaryResults[feature.properties.id]
          if result
            feature.properties.scores = result.percentage
            feature.properties.color = calculateColor(result.percentage)
          else
            feature.properties.scores = 0
            feature.properties.color = calculateColor(0)

          feature.properties.borderColor = 'white'

        boundaries = L.geoJson(data, { style: visibleStyle, onEachFeature: onEachFeature })
        boundaries.addTo(map)

        if boundaryId
          states.resetStyle(target)
          map.removeLayer(states)
        else
          states = boundaries
          stateResults = boundaryResults

        $("#" + id + "-placeholder").hide()
        map.fitBounds(boundaries.getBounds(), {step: .25})

        map.on 'resize', (e) ->
          map.fitBounds(boundaries.getBounds(), {step: .25})


  onEachFeature = (feature, layer) ->
      layer.on
        mouseover: highlightFeature
        mouseout: resetHighlight
        click: clickFeature

  # turn off leaflet credits
  map.attributionControl.setPrefix('')

  scale = L.control({position: 'topright'})

  scale.onAdd = (map) ->
    @_div = L.DomUtil.create('div', 'scale')
    @update()
    return @_div

  scale.update = (level=null) ->
    html = ""

    scaleClass = 'national'
    if level and level == STATE_LEVEL
      scaleClass = 'state'
    if level and level == DISTRICT_LEVEL
      scaleClass = 'district'

    html = "<div class='scale " + scaleClass + "'>"
    html += "<div class='scale-map-circle-outer primary-border-color'></div>"
    html += "<div class='scale-map-circle-inner'></div>"
    html += "<div class='scale-map-hline primary-border-color'></div>"
    html += "<div class='scale-map-vline primary-border-color'></div>"
    html += "<div class='scale-map-vline-2 primary-border-color'></div>"
    html += "<div class='national-level primary-color'>" + window.string_National.toUpperCase() + "</div>"
    html += "<div class='state-level primary-color'>" + window.string_State.toUpperCase() + "</div>"
    html += "<div class='district-level primary-color'>" + window.string_District.toUpperCase() + "</div>"

    @_div.innerHTML = html


  # this is our info box floating off in the upper right
  info = L.control({position: 'topleft'})

  info.onAdd = (map) ->
    @_div = L.DomUtil.create('div', 'info')
    @update()
    return @_div

  info.update = (props) ->
    html = ""

    label = mainLabelName
    results = overallResults
    if props? and props.id of boundaryResults
      label = props.name
      results = boundaryResults[props.id]

    # wait until we have the totalRegistered to avoid division by zero
    if topCategory
      html = "<div class='info'>"
      html += "<h2 class='admin-name'>" + label + "</h2>"

      html += "<div class='top-border primary-color'>" + window.string_Participation_Level.toUpperCase() + "</div>"
      html += "<div><table><tr><td class='info-count'>" + window.intcomma(results.set) + "</td><td class='info-count'>" + window.intcomma(results.set + results.unset) + "</td></tr>"
      html += "<tr><td class='info-tiny'>" + window.string_Responses + "</td><td class='info-tiny'>" + window.string_Reporters_in + " " + label + "</td></tr></table></div>"

      html += "<div class='top-border primary-color'>" + window.string_Results.toUpperCase() + "</div>"

      percentage = results.percentage
      if percentage < 0 or results.set == 0
        percentageTop = "--"
        percentageOther = "--"
      else
        percentageTop = percentage + "%"
        percentageOther = (100 - percentage) + "%"

      html += "<div class='results'><table width='100%'>"


      html += "<tr class='row-top'><td class='info-percentage'>" + percentageTop + "</td>"
      html += "<td class='info-label'>" + topCategory + "</td></tr>"

      html += "<tr class='row-other'><td class='info-percentage other-color top-border primary-border-color'>" + percentageOther + "</td>"
      html += "<td class='info-label top-border primary-border-color'>" + otherCategory + "</td></tr>"

      html += "</table></div>"

      if displayOthers and results.set > 0
        html += "<div class='other-details'>"
        html += "<div class='other-help'>"
        html += window.string_Other_answers
        html += ":</div><table>"
        for label, count of results.others
          percentage = Math.round((100 * count) / results.set)
          html += "<tr>"
          html += "<td class='detail-percentage'>" + percentage + "%</td>"
          html += "<td class='detail-label'>" + label + "</td>"
          html += "</tr>"
        html += "</table></div>"

      html += "</div>"

    @_div.innerHTML = html


  info.addTo(map)
  scale.addTo(map)
  states = L.geoJson(geojson, { style: visibleStyle, onEachFeature: onEachFeature })
  states.addTo(map)

  loadBoundary(null, null)
  map

# global context for this guy
window.initMap = initMap

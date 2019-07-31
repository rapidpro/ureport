initMap = (id, geojson, question, districtZoom, wardZoom, colorsList=[]) ->
  map = L.map(id, {scrollWheelZoom: false, zoomControl: false, touchZoom: false, trackResize: true,  dragging: false}).setView([0, 0], 8)
  STATE_LEVEL = 1
  DISTRICT_LEVEL = 2
  WARD_LEVEL = 3

  boundaries = null
  boundaryResults = null

  states = null
  stateResults = null

  info = null

  overallResults = null
  countryResults = null

  topBoundary = null
  
  topCategory = null
  otherCategory = null
  displayOthers = false

  mainLabelName = window.string_All

  colors = colorsList

  if not colors or colors.length != 11
    colors = ['rgb(221, 221, 221)',
              #'rgb(200, 214, 203)',
              'rgb(179, 207, 185)',
              #'rgb(158, 201, 167)',
              'rgb(137, 194, 149)',
              #'rgb(117, 188, 132)',
              'rgb(96, 181, 114)',
              #'rgb(75, 174, 96)',
              'rgb(54, 168, 78)',
              #'rgb(33, 161, 60)',
              'rgb(13, 155, 43)']

  breaks = [0, 
            #10, 
            20, 
            #30, 
            40, 
            #50, 
            60, 
            
            #70, 
            80, 
            #90, 
            100]

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

  updateLegend = (map, topBoundary) ->
    div = L.DomUtil.create("div", "info legend")

    # loop through our density intervals and generate a label with a colored square for each interval
    i = 0

    while i < breaks.length
      idx = breaks.length - i - 1

      upper = breaks[idx]

      if topBoundary
        div.innerHTML += "<i style=\"background:" + colors[idx] + "\"></i><br/>" ## + upper + "<b>%</> <br/>" ##+  window.string_of + " " + window.string_the + " " + topBoundary.label + " " + window.string_total + "<br/>"
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
    if not layer.feature.properties.level or layer.feature.properties.level == STATE_LEVEL and boundaries is states or layer.feature.properties.level in [DISTRICT_LEVEL, WARD_LEVEL] and boundaries isnt states
      layer.setStyle(HIGHLIGHT_STYLE)
      html = "<div class='popup-region-name'>" + layer.feature.properties.name + "</div>"+"<div class='popup-responses-number'>"+layer.feature.properties.responses+" Responses</div>"
      L.popup().setLatLng(e.latlng).setContent(html).openOn(map)

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
    if (districtZoom and e.target.feature.properties.level == STATE_LEVEL)
      mainLabelName = e.target.feature.properties.name + " (" + window.string_State + ")"
      loadBoundary(e.target.feature.properties, e.target)
      scale.update(e.target.feature.properties.level)
    else if (wardZoom and e.target.feature.properties.level == DISTRICT_LEVEL)
      map.removeLayer(boundaries)
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
      if not topBoundary
        boundaryCounts = {}
        topPopulated = -1

        for boundary in data
          boundary.population = boundary.set
          if boundary.population > topPopulated
            topPopulated = boundary.population
            topBoundary = boundary

        # add our legend
        legend = L.control(position: "bottomright")
        legend.onAdd = (map) -> updateLegend(map, topBoundary)
        legend.addTo(map)
      
      boundaryResults = {}
      for boundary in data
        if topBoundary.population
          boundary.percentage = Math.round((100 * boundary.set) / topBoundary.population)
        else
          boundary.percentage = 0
        boundaryResults[boundary['boundary']] = boundary

      # update our summary total
      info.update()
      scale.update(boundaryLevel)

      # we are displaying the districts of a state, load the geojson for it
      boundaryUrl = '/boundaries/'
      if boundaryId
        boundaryUrl += boundaryId + '/'

      $.ajax({url:boundaryUrl, dataType: "json"}).done (data) ->
        # added to reset boundary when district has no wards
        if data.features.length == 0
          resetBoundaries()
          scale.update()
          return
        for feature in data.features
          result = boundaryResults[feature.properties.id]
          if result
            feature.properties.scores = result.percentage
            feature.properties.responses = result.set
            feature.properties.color = calculateColor(result.percentage)
          else
            feature.properties.scores = 0
            feature.properties.responses = 0
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
    else if level and level == DISTRICT_LEVEL
      scaleClass = 'district'

    html = "<div class='scale " + scaleClass + "'>"
    html += "<div class='scale-map-circle-outer primary-border-color'></div>"
    html += "<div class='scale-map-circle-inner'></div>"
    html += "<div class='scale-map-hline primary-border-color'></div>"
    html += "<div class='scale-map-vline primary-border-color'></div>"
    html += "<div class='scale-map-vline-extended primary-border-color'></div>"
    html += "<div class='national-level primary-color'>" + window.string_All.toUpperCase() + "</div>"
    html += "<div class='state-level primary-color'>" + window.string_State.toUpperCase() + "</div>"
    html += "<div class='district-level primary-color'>" + window.string_District.toUpperCase() + "</div>"

    @_div.innerHTML = ""


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
      if not results
        results =
          set:0
          percentage:0

    # wait until we have the totalRegistered to avoid division by zero
    if topCategory
      html = "<div class='info'>"
      html += "<h2 class='admin-name'>" + label + "</h2>"

      html += "<div class='bottom-border info-title primary-color'>" + window.string_Participation_Level.toUpperCase() + "</div>"
      html += "<div><table><tr><td class='info-count'>" + window.intcomma(results.set) + "</td><td class='info-count'>" + window.intcomma(results.set + results.unset) + "</td></tr>"
      html += "<tr><td class='info-tiny'>" + window.string_Responses + "</td><td class='info-tiny'>" + window.string_Reporters_in + " " + label + "</td></tr></table></div>"

      html += "<div class='bottom-border info-title primary-color'>" + window.string_Results.toUpperCase() + "</div>"

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

      html += "<tr class='row-other'><td class='info-percentage other-color primary-border-color'>" + percentageOther + "</td>"
      html += "<td class='info-label primary-border-color'>" + otherCategory + "</td></tr>"

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

    @_div.innerHTML = ""


  info.addTo(map)
  scale.addTo(map)
  states = L.geoJson(geojson, { style: visibleStyle, onEachFeature: onEachFeature })
  states.addTo(map)

  loadBoundary(null, null)
  map

# global context for this guy
window.initMap = initMap

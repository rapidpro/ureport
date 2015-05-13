initMap = (id, geojson, ajaxUrl, colorsList=[]) ->
  map = L.map(id, {scrollWheelZoom: false, zoomControl: false, touchZoom: false, trackResize: true,  dragging: false}).setView([0, 0], 8)

  boundaries = null
  boundaryResults = null

  states = null
  stateResults = null

  info = null

  totalRegistered = 0
  topPopulated = 0

  topBoundary = null

  mainLabelName = "All"
  mainLabelRegistered = 0

  colors = colorsList

  if not colors
    colors = ['rgb(217,240,163)','rgb(173,221,142)','rgb(120,198,121)','rgb(65,171,93)','rgb(35,132,67)','rgb(0,104,55)']

  breaks = [0, 20, 40, 60, 80, 100]

  visibleStyle = (feature) ->
    return {
      weight: 2
      opacity: 1
      color: 'white'
      fillOpacity: 1
      fillColor: feature.properties.color
    }

  fadeStyle = (feature) ->
    return {
      weight: 2
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
        div.innerHTML += "<i style=\"background:" + colors[idx] + "\"></i> " + upper + "% of the " + topBoundary.label + " total<br/>"
      
      i++

    return div

  calculateColor = (percentage) ->
    if percentage < 0
      return 'rgb(200, 200, 200)'

    for cutoff, i in breaks
      if cutoff >= percentage
        return colors[i]

  HIGHLIGHT_STYLE =
    weight: 6
    fillOpacity: 1

  highlightFeature = (e) ->
    layer = e.target
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
    map.fitBounds(states.getBounds(), {paddingTopLeft: [200, 0]})

  resetHighlight = (e) ->
    states.resetStyle(e.target)
    info.update()

  clickFeature = (e) ->
    if (e.target.feature.properties.level == 1)
      map.fitBounds(e.target.getBounds(), {paddingTopLeft: [200, 0]})
      mainLabelName = e.target.feature.properties.name + " (State)"
      loadBoundary(e.target.feature.properties.id, e.target)
      scale.update(e.target.feature.properties.level)
    else
      resetBoundaries()
      scale.update()
      mainLabelName = "All"
      mainLabelRegistered = totalRegistered

  loadBoundary = (boundaryId, target) ->
    # load our actual data
    if not boundaryId
      segment = {location:"State"}
    else
      segment = {location:"District", parent:boundaryId}

    $.ajax({url: ajaxUrl + '&segment=' + encodeURIComponent(JSON.stringify(segment)), dataType: "json"}).done (data) ->
      # calculate the most common category if we haven't already
      if not topBoundary
        boundaryCounts = {}
        topPopulated = -1

        for boundary in data
          totalRegistered += boundary.set + boundary.unset
          boundary.population = boundary.set + boundary.unset
          if boundary.population > topPopulated
            topPopulated = boundary.population
            topBoundary = boundary

        # add our legend
        legend = L.control(position: "bottomright")
        legend.onAdd = (map) -> updateLegend(map, topBoundary)
        legend.addTo(map)

      mainLabelRegistered = 0
      boundaryResults = {}
      for boundary in data
        if topBoundary.population
          boundary.percentage = Math.round((100 * (boundary.set + boundary.unset)) / topBoundary.population)
        else
          boundary.percentage = 0
        boundaryResults[boundary['boundary']] = boundary
        mainLabelRegistered += boundary.set + boundary.unset
        info.update()
        scale.update(boundaryId)

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
        map.fitBounds(boundaries.getBounds(), {paddingTopLeft: [200, 0]})

        map.on 'resize', (e) ->
          map.fitBounds(boundaries.getBounds())

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
    if level
      scaleClass = 'state'

    html = "<div class='scale " + scaleClass + "'>"
    html += "<div class='scale-map-circle-outer primary-border-color'></div>"
    html += "<div class='scale-map-circle-inner'></div>"
    html += "<div class='scale-map-hline primary-border-color'></div>"
    html += "<div class='scale-map-vline primary-border-color'></div>"
    html += "<div class='national-level primary-color'>NATIONAL</div>"
    html += "<div class='state-level primary-color'>STATE</div>"

    @_div.innerHTML = html


  # this is our info box floating off in the upper right
  info = L.control({position: 'topleft'})

  info.onAdd = (map) ->
    @_div = L.DomUtil.create('div', 'info')
    @update()
    return @_div

  info.update = (props) ->
    html = ""

    if mainLabelRegistered
      html = "<div class='info'>"
      html += "<h2 class='admin-name'>" + mainLabelName + "</h2>"

      html += "<div class='top-border primary-color'>POPULATION</div>"
      html += "<div><table><tr><td class='info-count'>" + intcomma(mainLabelRegistered) + "</td></tr>"
      html += "<tr><td class='info-tiny'>Registered in " + mainLabelName + "</td></tr></table></div>"

    if props?
      result = boundaryResults[props.id]
      if not result
        result =
          set:0
          unset:0

      html = "<div class='info'>"
      html += "<h2 class='admin-name'>" + props.name + "</h2>"

      html += "<div class='top-border primary-color'>POPULATION</div>"
      html += "<div><table><tr><td class='info-count'>" + intcomma(result.set + result.unset) + "</td></tr>"
      html += "<tr><td class='info-tiny'>Registered in " + props.name + "</td></tr></table></div>"

      html += "<div class='top-border primary-color'>DENSITY</div>"

      percentage = result.percentage
      if percentage < 0
        percentageTop = "--"
      else
        percentageTop = percentage + "%"

      html += "<div class='info-percentage top-color'>" + percentageTop + "</div>"
      html += "<div class='info-tiny'>of the " + topBoundary.label + " total</div>"

      html += "</div>"

    @_div.innerHTML = html


  info.addTo(map)
  scale.addTo(map)
  states = L.geoJson(geojson, { style: visibleStyle, onEachFeature: onEachFeature })
  states.addTo(map)

  loadBoundary(null, null)

# global context for this guy
window.initMap = initMap

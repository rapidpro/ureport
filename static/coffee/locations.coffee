
intcomma = (value) ->
  origValue = String(value);
  newValue = origValue.replace(/^(-?\d+)(\d{3})/, '$1,$2')
  if origValue == newValue
    return newValue
  else
    return intcomma(newValue)

initMap = (id, geojson, question) ->
  map = L.map(id, {scrollWheelZoom: false, zoomControl: false, touchZoom: false, trackResize: true,  dragging: false}).setView([0, 0], 8)

  boundaries = null
  boundaryResults = null

  states = null
  stateResults = null

  info = null

  totalAnswered = 0
  totalRegistered = 0

  topCategory = null

  totalTop = -1
  totalOther = -1

  mainLabelName = "All States"

  colors = ['rgb(165,0,38)','rgb(215,48,39)','rgb(244,109,67)','rgb(253,174,97)','rgb(254,224,139)','rgb(255,255,191)','rgb(217,239,139)','rgb(166,217,106)','rgb(102,189,99)','rgb(26,152,80)','rgb(0,104,55)']

  breaks = [20, 30, 35, 40, 45, 55, 60, 65, 70, 80, 100]

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

  updateLegend = (map, topCategory) ->
    div = L.DomUtil.create("div", "info legend")

    # loop through our density intervals and generate a label with a colored square for each interval
    i = 0

    while i < breaks.length
      idx = breaks.length - i - 1

      lower = if idx > 0 then breaks[idx-1] else 0
      upper = breaks[idx]

      if lower < 50 and upper < 50
        category = "Other"
        upper = 100 - upper

        div.innerHTML += "<i style=\"background:" + colors[idx] + "\"></i> " + upper + "% " + category + "<br/>"

      else if lower > 50 and upper > 50
        category = topCategory

        div.innerHTML += "<i style=\"background:" + colors[idx] + "\"></i> " + lower + "% " + category + "<br/>"
      else
        div.innerHTML += "<i style=\"background:" + colors[i] + "\"></i>Even<br/>"
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
      mainLabelName = "All States"



  loadBoundary = (boundaryId, target) ->
    # load our actual data
    if not boundaryId
      segment = {location:"State"}
    else
      segment = {location:"District", parent:boundaryId}

    $.ajax({url:'/pollquestion/' + question + '/results/?segment=' + encodeURIComponent(JSON.stringify(segment)), dataType: "json"}).done (data) ->
      # calculate the most common category if we haven't already
      if not topCategory
        categoryCounts = {}
        totalRegistered = 0
        totalAnswered = 0

        for boundary in data
          for category in boundary['categories']
            if category.label of categoryCounts
              categoryCounts[category.label] += category.count
            else
              categoryCounts[category.label] = category.count

          totalRegistered += (boundary.set + boundary.unset)
          totalAnswered += boundary.set

        totalTop = -1
        for category, count of categoryCounts
          if count > totalTop
            totalTop = count
            topCategory = category

        # our total for others
        totalOther = 0
        for category, count of categoryCounts
          if category != topCategory
            totalOther += count

        # add our legend
        legend = L.control(position: "bottomright")
        legend.onAdd = (map) -> updateLegend(map, topCategory)
        legend.addTo(map)

      # update our summary total
      info.update()
      scale.update(boundaryId)

      # now calculate the percentage for each admin boundary
      boundaryResults = {}
      for boundary in data
        # calculate the percentage of our top category vs the others
        boundary.percentage = -1

        for category in boundary['categories']
          if category.label == topCategory and boundary.set
            boundary.percentage = Math.round((100 * category.count) / boundary.set)
            break

        boundaryResults[boundary['boundary']] = boundary

      # we are displaying the districts of a state, load the geojson for it
      boundaryUrl = '/boundaries/'
      if boundaryId
        boundaryUrl += boundaryId + '/'

      $.ajax({url:boundaryUrl, dataType: "json"}).done (data) ->
        for feature in data.features
          result = boundaryResults[feature.properties.id]
          feature.properties.scores = result.percentage
          feature.properties.color = calculateColor(result.percentage)
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

    # wait until we have the totalRegistered to avoid division by zero
    if topCategory
      html = "<div class='info'>"
      html += "<h2 class='admin-name'>" + mainLabelName + "</h2>"

      html += "<div class='top-border'>PARTICIPATION LEVEL</div>"
      html += "<div><table><tr><td class='info-count'>" + intcomma(totalTop+totalOther) + "</td><td class='info-count'>" + intcomma(totalRegistered) + "</td></tr>"
      html += "<tr><td class='info-tiny'>Responses</td><td class='info-tiny'>Reporters in " + mainLabelName + "</td></tr></table></div>"

      html += "<div class='top-border'>RESULTS</div>"

      percentage = Math.round((100 * totalTop) / (totalTop + totalOther))
      if percentage < 0
        percentageTop = "--"
        percentageOther = "--"
      else
        percentageTop = percentage + "%"
        percentageOther = (100 - percentage) + "%"

      html += "<div class='info-percentage top-color'>" + percentageTop + "</div>"
      html += "<div class='info-tiny'>" + topCategory + "</div>"

      html += "<div class='info-percentage other-color top-border' style='padding-top: 10px'>" + percentageOther + "</div>"
      html += "<div class='info-tiny'>Other</div>"

      html += "</div>"
 
    if props?
      result = boundaryResults[props.id]

      html = "<div class='info'>"
      html += "<h2 class='admin-name'>" + props.name + "</h2>"

      html += "<div class='top-border'>PARTICIPATION LEVEL</div>"
      html += "<div><table><tr><td class='info-count'>" + intcomma(result.set) + "</td><td class='info-count'>" + intcomma(result.set + result.unset) + "</td></tr>"
      html += "<tr><td class='info-tiny'>Responses</td><td class='info-tiny'>Reporters in " + props.name + "</td></tr></table></div>"

      html += "<div class='top-border'>RESULTS</div>"

      percentage = result.percentage
      if percentage < 0
        percentageTop = "--"
        percentageOther = "--"
      else
        percentageTop = percentage + " %"
        percentageOther = (100 - percentage) + " %"

      html += "<div class='info-percentage top-color'>" + percentageTop + "</div>"
      html += "<div class='info-tiny'>" + topCategory + "</div>"

      html += "<div class='info-percentage other-color top-border' style='padding-top: 10px'>" + percentageOther + "</div>"
      html += "<div class='info-tiny'>Other</div>"

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

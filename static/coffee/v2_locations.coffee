$(->
  # generate our gradient
  colors = gradientFactory.generate({
    from: '#DDDDDD'
    to: primaryColor
    stops: 7
  })

  # breaks for each gradient
  breaks = [0, 5, 10, 25, 45, 65, 85]

  # default empty style
  emptyStyle = (feature) ->
    return {
      fillColor: colors[1]
      weight: 1
      opacity: 1
      color: 'white'
      fillOpacity: 0.7
    }

  highlightStyle = {
    weight: 3
    fillOpacity: 1
  }

  # our leaflet options
  options = {
      # no user controlled zooming
      zoomControl:false
      scrollWheelZoom: false
      doubleClickZoom: false
      boxZoom: false

      # allow arbitrary scaling
      zoomSnap: 0

      # remove leaflet attribution
      attributionControl: false

      # don't allow dragging
      dragging: false
  }



  initMap = (id, geojson, url, districtZoom, wardZoom) ->
    map = L.map(id, options)

    # constants
    STATE_LEVEL = 1
    DISTRICT_LEVEL = 2
    WARD_LEVEL = 3
  
    boundaries = null
    countMap = null
  
    states = null
    stateResults = null

    topBoundary = null
  
    info = null
    
    # this is our info box floating off in the top right
    info = new L.control()
  
    info.onAdd = (map) ->
      this._div = L.DomUtil.create('div', 'leaflet-info');
      newParent = document.getElementById('map-info')
      oldParent = document.getElementsByClassName('leaflet-control-container')[0]
      newParent.appendChild(oldParent)
      
      this.update()
      return this._div
    
    info.update = (props) ->
      if props
        if props.count?
          if props.count.unset?
            total = props.count.set + props.count.unset
            this._div.innerHTML = "<div class='name'>" + props.name + "</div>" +
              "<div class='count'>" + props.count.set.toLocaleString() + " " + window.string_Responders + " // " + total.toLocaleString() + " " + window.string_Polled + "</div>"
          else if props.count.set?
            this._div.innerHTML = "<div class='name'>" + props.name + "</div>" +
              "<div class='count'>" + props.count.set.toLocaleString() + " " + window.string_Reporters + "</div>"
          else
            this._div.innerHTML = "<div class='name'>" + props.name + "</div>"
        else
          this._div.innerHTML = ""
      else
        if topBoundary?
          if topBoundary.unset?
            total = topBoundary.set + topBoundary.unset
            this._div.innerHTML = "<div class='label'>" + window.string_TopRegion + ":</div><div class='name'>" + topBoundary.label + "</div>" +
                "<div class='count'>" + topBoundary.set.toLocaleString() + " " + window.string_Responders + " // " + total.toLocaleString() + " " + window.string_Polled + "</div>"
          else if topBoundary.set?
            this._div.innerHTML = "<div class='label'>" + window.string_TopRegion + ":</div><div class='name'>" + topBoundary.label + "</div>" +
                "<div class='count'>" + topBoundary.set.toLocaleString() + " " + window.string_Reporters + "</div>"
          else
            this._div.innerHTML = "<div class='label'>" + window.string_TopRegion + ":</div><div class='name'>" + topBoundary.label + "</div>"
        else
           this._div.innerHTML = ""
    
    # rollover treatment
    highlight = (e) ->
      layer = e.target
      if not layer.feature.properties.level or layer.feature.properties.level == STATE_LEVEL and boundaries is states or layer.feature.properties.level in [DISTRICT_LEVEL, WARD_LEVEL] and boundaries isnt states
        layer.setStyle(highlightStyle)
        if (!L.Browser.ie && !L.Browser.opera)
          layer.bringToFront()

      info.update(layer.feature.properties)
  
    clickFeature = (e) ->
      if (not districtZoom and not wardZoom)
        highlight(e)
        return
      if (districtZoom and e.target.feature.properties.level == STATE_LEVEL)
        map.removeLayer(states)
        loadBoundary(url, e.target.feature.properties, e.target)
      else if (wardZoom and e.target.feature.properties.level == DISTRICT_LEVEL)
        map.removeLayer(boundaries)
        loadBoundary(url, e.target.feature.properties, e.target)
      else
        resetBoundaries()
  
    # resets our color on mouseout
    reset = (e) ->
      states.resetStyle(e.target)
      info.update()
    
    # looks up the color for the passed in feature
    countStyle = (feature) ->
      return {
        fillColor: feature.properties.color
        weight: 1
        opacity: 1
        color: 'white'
        fillOpacity: 0.7
      }
  
    onEachFeature = (feature, layer) ->
      layer.on({
        mouseover: highlight
        mouseout: reset
        click: clickFeature
      });
  
    resetBoundaries = ->
      map.removeLayer(boundaries) 
  
      boundaries = states
      countMap = stateResults
  
      states.setStyle(countStyle)
      map.addLayer(states)
      bounds = states.getBounds()
      map.fitBounds([
        [bounds.getNorth(), bounds.getEast() ? bounds.getEast() > 0 : bounds.getEast() + 360],
        [bounds.getNorth(), bounds.getWest() ? bounds.getWest() > 0 : bounds.getWest() + 360]
      ])
  
      info.update()
  
    loadBoundary = (url, boundary, target) ->
      boundaryId = if boundary then boundary.id else null
      boundaryLevel = if boundary then boundary.level else null
  
      # load our actual data
      if not boundary
        segment = {location:"State"}
      else if boundary and boundary.level == DISTRICT_LEVEL
        segment = {location:"Ward", parent:boundaryId}
      else
        segment = {location:"District", parent:boundaryId}
  
      $.ajax({url: url + '?segment=' + encodeURIComponent(JSON.stringify(segment)), dataType: "json"}).done (counts) ->
        countMap = {}
  
        # figure out our max value
        max = 0;
        for count in counts
          countMap[count.boundary] = count
          if (count.set > max)
            max = count.set
            topBoundary = count

        # and create mapping of threshold values to colors
        colorSteps = []
        for color, i in colors
          colorSteps[i] = {
            threshold: max * (breaks[i] / 100)
            color: colors[i]
          }
  

        # we are displaying the districts of a state, load the geojson for it
        boundaryUrl = '/boundaries/'
        if boundaryId
          boundaryUrl += boundaryId + '/'
  
        $.ajax({url:boundaryUrl, dataType: "json"}).done (data) ->
          # added to reset boundary when district has no wards
          if data.features.length == 0
            resetBoundaries()
            return

          for feature in data.features
            props = feature.properties
            count = countMap[props.id].set
  
            # merge our count values in
            props.count = countMap[props.id]
  
            props.color = colorSteps[colorSteps.length-1].color
            for step in colorSteps
              if count <= step.threshold
                props.color = step.color
                break

          boundaries = L.geoJSON(data, {
            style: countStyle,
            onEachFeature: onEachFeature
          })
          boundaries.addTo(map);

          if boundaryId
            states.resetStyle(target)
            map.removeLayer(states)
          else
            states = boundaries
            stateResults = countMap
          
          $("#poll-map-placeholder").addClass('hidden')
          bounds = boundaries.getBounds()
          map.fitBounds([
            [bounds.getNorth(), bounds.getEast() ? bounds.getEast() > 0 : bounds.getEast() + 360 ],
            [bounds.getNorth(), bounds.getWest() ? bounds.getWest() > 0 : bounds.getWest() + 360]
          ]);
          map.on 'resize', (e) ->
            map.fitBounds([
              [bounds.getNorth(), bounds.getEast() ? bounds.getEast() > 0 : bounds.getEast() + 360],
              [bounds.getNorth(), bounds.getWest() ? bounds.getWest() > 0 : bounds.getWest() + 360]
            ])
          info.update()

    info.addTo(map);
    loadBoundary(url, null, null)
    map

  if $(".map").length > 0
    # fetch our top level states
    $.ajax({url:'/boundaries/', dataType: "json"}).done((states) ->
      # now that we have states, initialize each map
      $(".map").each(->
        url = $(this).data("map-url")
        id = $(this).attr("id")
        districtZoom = $(this).data("district-zoom")
        wardZoom = $(this).data("ward-zoom")

        # no id? can't render, warn in console
        if (id == undefined)
          console.log("missing map id, not rendering")
          return

        # no url? render empty map
        if (url == undefined)
          console.log("missing map url, rendering empty")
          map = L.map(id, options)
          boundaries = L.geoJSON(states, {style: emptyStyle})
          boundaries.addTo(map);
          bounds = boundaries.getBounds()
          map.fitBounds([
            [bounds.getNorth(), bounds.getEast() ? bounds.getEast() > 0 : bounds.getEast() + 360 ],
            [bounds.getNorth(), bounds.getWest() ? bounds.getWest() > 0 : bounds.getWest() + 360]
          ]);
          return

        map = initMap(id, states, url, districtZoom, wardZoom)

      )
    )
)
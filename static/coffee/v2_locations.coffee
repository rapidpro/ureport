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

  # fetch our top level states
  $.ajax({url:'/boundaries/', dataType: "json"}).done((states) ->
    # now that we have states, initialize each map
    $(".map").each(->
      url = $(this).data("map-url")
      id = $(this).attr("id")

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
        map.fitBounds(boundaries.getBounds());
        return

      # if we have a URL load our data
      $.getJSON(url, (counts) ->
        countMap = {}

        # figure out our max value
        max = 0;
        for count in counts
          countMap[count.boundary] = count
          if (count.set > max)
            max = count.set

        # and create mapping of threshold values to colors
        colorSteps = []
        for color, i in colors
          colorSteps[i] = {
            threshold: max * (breaks[i] / 100)
            color: colors[i]
          }

        # clone our states
        states = JSON.parse(JSON.stringify(states))

        # iterate through and assign colors
        for state in states.features
          props = state.properties
          count = countMap[props.id].set

          # merge our count values in
          props.count = countMap[props.id]

          props.color = colorSteps[colorSteps.length-1].color
          for step in colorSteps
            if count <= step.threshold
                props.color = step.color
                break

        # looks up the color for the passed in feature
        countStyle = (feature) ->
          return {
              fillColor: feature.properties.color
              weight: 1
              opacity: 1
              color: 'white'
              fillOpacity: 0.7
          }

        boundaries = null;

        # this is our info box floating off in the top right
        info = new L.control()

        info.onAdd = (map) ->
          this._div = L.DomUtil.create('div', 'leaflet-info');
          this.update()
          return this._div

        info.update = (props) ->
          if props
            total = props.count.set + props.count.unset
            this._div.innerHTML = "<div class='name'>" + props.name + "</div>" +
              "<div class='count'>" + props.count.set + " of " + total + "</div>"
          else
            this._div.innerHTML = ""

        # rollover treatment
        highlight = (e) ->
          layer = e.target
          layer.setStyle(highlightStyle)
          if (!L.Browser.ie && !L.Browser.opera && !L.Browser.edge)
            layer.bringToFront()

          info.update(e.target.feature.properties)

        # resets our color on mouseout
        reset = (e) ->
          boundaries.resetStyle(e.target)
          info.update()

        map = L.map(id, options)
        boundaries = L.geoJSON(states, {
          style: countStyle,
          onEachFeature: (feature, layer) ->
            layer.on({
              mouseover: highlight
              mouseout: reset
            });
        })
        boundaries.addTo(map);
        info.addTo(map);
        map.fitBounds(boundaries.getBounds());
      )
    )
  )
)
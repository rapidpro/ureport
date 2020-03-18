# wire in our search boxes
$(->
  $(".search-box").focusin(->
    searchBox = $(this)
    results = "#" + $(this).data("results-id")
    if not $(results).hasClass("shown")
      $(results).addClass("shown")
      $(document).click(->
        $(searchBox).val("")
        $(results).find(".no-results").addClass("hidden")
        $(results).find(".searchable").removeClass("hide")
        $(results).find(".search-category").removeClass("hidden").removeClass("open")
        $(results).removeClass("shown")
        $(document).unbind("click")
      )
  )

  # don't bubble events past our search results or box
  $(".search-results,.search-box").click((e) ->
    e.stopPropagation()
  )

  $(".search-category > a").click((e)->
    category = $(this).parent()
    open = $(category).hasClass("open")
    $(category).data("state", if open then "closed" else "open")
    $(category).toggleClass("open")
    e.stopPropagation()
    return false
  )

  $(".search-box").keyup(->
    filter = $(this).val().toLowerCase()
    results = $(this).data("results-id")

    # no search, make everything visible again
    if filter == ""
      $("#" + results).find(".search-category").each(->
        console.log(this)
        $(this).removeClass("hidden")
        console.log("state: " + $(this).data("state"))
        if $(this).data("state") == "open"
          $(this).addClass("open")
        else
          $(this).removeClass("open")
      )
      $("#" + results).find(".searchable").removeClass("hide")
      $("#" + results).find(".no-results").addClass("hidden")
      return

    # for each category
    total_count = 0
    $("#" + results).find(".search-category").each(->
      # find all items that match
      count = 0
      $(this).find(".searchable").each(->
        value = $(this).data("search-value")
        if value.toLowerCase().indexOf(filter) >= 0
          $(this).removeClass("hide")
          count += 1
        else
          $(this).addClass("hide")
      )

      # hide or not based on our count
      if count > 0
        $(this).removeClass("hidden").addClass("open")
      else
        $(this).addClass("hidden")

      total_count += count
    )

    if total_count == 0
      $("#" + results).find(".no-results").removeClass("hidden")
    else
      $("#" + results).find(".no-results").addClass("hidden")
  )
)
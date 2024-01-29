# wire in our countries dropdown
$(->

  $(".region-dropdown > a").click((e)->
    category = $(this).parent()
    open = $(category).hasClass("open")
    $(category).data("state", if open then "closed" else "open")
    $(category).siblings().removeClass("open")
    $(category).toggleClass("open")
    e.stopPropagation()
    return false
  )

)
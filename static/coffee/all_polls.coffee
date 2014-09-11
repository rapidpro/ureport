$(->
  $("input.category").change ->
    catId = $(this).attr("value")
    console.log(catId)
    if catId == "-1"
      $("li.poll").show()
    else
      $("li.poll").hide()
      $("li.poll[data-category=" + catId + "]").show()
)
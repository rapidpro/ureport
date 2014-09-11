$(->
  $(".featured-stories-filters input.category").change ->
    catId = $(this).attr("value")
    console.log(catId)
    if catId == "-1"
      $(".story-filtered").show()
    else
      $(".story-filtered").hide()
      $(".story-filtered[data-category=" + catId + "]").show()
)
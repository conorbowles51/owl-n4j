import pytest
from app.pipeline.ocr_geometry import project_ocr_words


def data(x=10,y=20,w=20,h=20):
    return dict(text=['12.34'],left=[x],top=[y],width=[w],height=[h])


def project(value, rotation=0):
    return project_ocr_words(value, rotation=rotation, image_width=100,image_height=200,page_width=500,page_height=1000)


@pytest.mark.parametrize('rotation,box', [(0,(10,20,20,20)), (90,(160,10,20,20)), (180,(70,160,20,20)), (270,(20,70,20,20))])
def test_orientation_is_undone_before_pixel_scaling(rotation,box):
    assert project(data(*box), rotation) == [(50,100,150,200,'12.34')]


@pytest.mark.parametrize('value', [data(-1),data(w=0),data(x=99),data(x=float('nan')),data(y=True),{'text':['12.34']}, {**data(),'height':[]}, {**data(),'text':[42]}])
def test_untrusted_geometry_is_refused_instead_of_partly_located(value):
    with pytest.raises(ValueError):project(value)


@pytest.mark.parametrize('rotation',[45,False,'90'])
def test_unknown_orientation_is_not_guessed(rotation):
    with pytest.raises(ValueError):project(data(),rotation)


def test_blank_tesseract_layout_entries_are_not_source_words():
    assert project(dict(text=['','12.34'],left=[0,10],top=[0,20],width=[0,20],height=[0,20])) == [(50,100,150,200,'12.34')]

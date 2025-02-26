import torch
import glob
import os
from argparse import ArgumentParser
from PIL import Image
from torchvision.transforms import functional as F
from tqdm import tqdm
from utilities.print_utils import *
from transforms.classification.data_transforms import MEAN, STD
from utilities.utils import model_parameters, compute_flops

# ===========================================
__author__ = "John Newton"
__license__ = "MIT"
__maintainer__ = "John Newton"
# ============================================

def relabel(img):
    '''
    This function relabels the predicted labels so that cityscape dataset can process
    :param img:
    :return:
    '''
    img[img == 19] = 255
    img[img == 18] = 33
    img[img == 17] = 32
    img[img == 16] = 31
    img[img == 15] = 28
    img[img == 14] = 27
    img[img == 13] = 26
    img[img == 12] = 25
    img[img == 11] = 24
    img[img == 10] = 23
    img[img == 9] = 22
    img[img == 8] = 21
    img[img == 7] = 20
    img[img == 6] = 19
    img[img == 5] = 17
    img[img == 4] = 13
    img[img == 3] = 12
    img[img == 2] = 11
    img[img == 1] = 8
    img[img == 0] = 7
    img[img == 255] = 0
    return img


def data_transform(img, im_size):
    img = img.resize(im_size, Image.BILINEAR)
    img = F.to_tensor(img)  # convert to tensor (values between 0 and 1)
    img = F.normalize(img, MEAN, STD)  # normalize the tensor
    return img


def evaluate(args, model, image_list, device):
    im_size = tuple(args.im_size)

    # get color map for pascal dataset
    if args.dataset == 'pascal':
        from utilities.color_map import VOCColormap
        cmap = VOCColormap().get_color_map_voc()
    else:
        cmap = None

    model.eval()
    for i, imgName in tqdm(enumerate(image_list)):
        img = Image.open(imgName).convert('RGB')
        w, h = img.size

        img = data_transform(img, im_size)
        img = img.unsqueeze(0)  # add a batch dimension
        img = img.to(device)
        img_out = model(img)
        img_out = img_out.squeeze(0)  # remove the batch dimension
        img_out = img_out.max(0)[1].byte()  # get the label map
        img_out = img_out.to(device='cpu').numpy()

        if args.dataset == 'city':
            # cityscape uses different IDs for training and testing
            # so, change from Train IDs to actual IDs
            img_out = relabel(img_out)

        img_out = Image.fromarray(img_out)
        # resize to original size
        img_out = img_out.resize((w, h), Image.NEAREST)

        # pascal dataset accepts colored segmentations
        if args.dataset == 'pascal':
            img_out.putpalette(cmap)

        # save the segmentation mask
        name = imgName.split('/')[-1]
        img_extn = imgName.split('.')[-1]
        name = '{}/{}'.format(args.savedir, name.replace(img_extn, 'png'))
        img_out.save(name)


def load_dataset(args):
    # read all the images in the folder
    if args.dataset == 'city':
        image_path = os.path.join(args.data_path, "leftImg8bit", args.split, "*", "*.png")
        image_list = glob.glob(image_path)
        from data_loader.segmentation.cityscapes import CITYSCAPE_CLASS_LIST
        seg_classes = len(CITYSCAPE_CLASS_LIST)
    elif args.dataset == 'pascal':
        from data_loader.segmentation.voc import VOC_CLASS_LIST
        seg_classes = len(VOC_CLASS_LIST)
        data_file = os.path.join(args.data_path, 'VOC2012', 'list', '{}.txt'.format(args.split))
        if not os.path.isfile(data_file):
            print_error_message('{} file does not exist'.format(data_file))
        image_list = []
        with open(data_file, 'r') as lines:
            for line in lines:
                rgb_img_loc = '{}/{}/{}'.format(args.data_path, 'VOC2012', line.split()[0])
                if not os.path.isfile(rgb_img_loc):
                    print_error_message('{} image file does not exist'.format(rgb_img_loc))
                image_list.append(rgb_img_loc)
    else:
        print_error_message('{} dataset not yet supported'.format(args.dataset))

    if len(image_list) == 0:
        print_error_message('No files in directory: {}'.format(image_path))
    image_list = image_list[:5]
    print_info_message('# of images for testing: {}'.format(len(image_list)))
    return image_list

def load_model(args):

    if args.model == 'espnetv2':
        from model.segmentation.espnetv2 import espnetv2_seg
        args.classes = args.num_classes
        model = espnetv2_seg(args)
    elif args.model == 'dicenet':
        from model.segmentation.dicenet import dicenet_seg
        model = dicenet_seg(args, classes=args.num_classes, scales=[1.0])
    else:
        print_error_message('{} network not yet supported'.format(args.model))
        exit(-1)

    # mdoel information
    num_params = model_parameters(model)
    # flops = compute_flops(model, input=torch.Tensor(1, 3, args.im_size[0], args.im_size[1]))
    # print_info_message('FLOPs for an input of size {}x{}: {:.2f} million'.format(args.im_size[0], args.im_size[1], flops))
    # print_info_message('# of parameters: {}'.format(num_params))

    if args.weights_test:
        print_info_message('Loading model weights')
        weight_dict = torch.load(args.weights_test, map_location=torch.device('cpu'))
        model.load_state_dict(weight_dict)
        print_info_message('Weight loaded successfully')
    else:
        print_error_message('weight file does not exist or not specified. Please check: {}', format(args.weights_test))

    num_gpus = torch.cuda.device_count()
    num_gpus = 0  # JN
    device = 'cuda' if num_gpus > 0 else 'cpu'
    model = model.to(device=device)
    return model, device
    # evaluate(args, model, image_list, device=device)

def load_args(in_args):

    from commons.general_details import segmentation_models, segmentation_datasets
    parser = ArgumentParser()

    # model details
    parser.add_argument('--dir', default='', help='Edgenets directory.')
    parser.add_argument('--model', default="espnetv2", choices=segmentation_models, help='Model name')
    parser.add_argument('--weights-test', default='', help='Pretrained weights directory.')
    parser.add_argument('--s', default=2.0, type=float, help='scale')
    # dataset details
    parser.add_argument('--data-path', default="/home/john/github/data/cityscapes/", help='Data directory')
    parser.add_argument('--dataset', default='city', choices=segmentation_datasets, help='Dataset name')
    # input details
    parser.add_argument('--im-size', type=int, nargs="+", default=[1024, 512], help='Image size for testing (W x H)')
    parser.add_argument('--split', default='val', choices=['val', 'test'], help='data split')
    parser.add_argument('--model-width', default=224, type=int, help='Model width')
    parser.add_argument('--model-height', default=224, type=int, help='Model height')
    parser.add_argument('--channels', default=3, type=int, help='Input channels')
    parser.add_argument('--num-classes', default=1000, type=int,
                        help='ImageNet classes. Required for loading the base network')

    args = parser.parse_args(in_args.split())

    if not args.weights_test:
        from model.weight_locations.segmentation import model_weight_map

        model_key = '{}_{}'.format(args.model, args.s)
        dataset_key = '{}_{}x{}'.format(args.dataset, args.im_size[0], args.im_size[1])
        assert model_key in model_weight_map.keys(), '{} does not exist'.format(model_key)
        assert dataset_key in model_weight_map[model_key].keys(), '{} does not exist'.format(dataset_key)
        args.weights_test = args.dir + model_weight_map[model_key][dataset_key]['weights']
        if not os.path.isfile(args.weights_test):
            print_error_message('weight file does not exist: {}'.format(args.weights_test))

    # set-up results path
    if args.dataset == 'city':
        args.savedir = '{}_{}_{}/results'.format('results', args.dataset, args.split)
    elif args.dataset == 'pascal':
        args.savedir = '{}_{}/results/VOC2012/Segmentation/comp6_{}_cls'.format('results', args.dataset, args.split)
    else:
        print_error_message('{} dataset not yet supported'.format(args.dataset))

    if not os.path.isdir(args.savedir):
        os.makedirs(args.savedir)

    # This key is used to load the ImageNet weights while training. So, set to empty to avoid errors
    args.weights = ''

    return args

def _freeze(model, freeze=True):
    for name, child in model.named_children():
        for param in child.parameters():
            param.requires_grad = not freeze
        _freeze(child, freeze=freeze)

def _count_freeze(model):
    count_requires_grad = 0
    count_not_requires_grad = 0
    for name, child in model.named_children():
        for param in child.parameters():
            if param.requires_grad == True:
                count_requires_grad += 1
            else:
                count_not_requires_grad += 1

        _count_freeze(child)
    return count_requires_grad, count_not_requires_grad

def freeze_base(model):
    _freeze(model.base_net, freeze=True)
    print(f'Parameters unfrozen = {_count_freeze(model)[0]}, Parameters frozen = {_count_freeze(model)[1]} ')

def unfreeze_base(model):
    _freeze(model.base_net, freeze=False)
    print(f'Parameters unfrozen = {_count_freeze(model)[0]}, Parameters frozen = {_count_freeze(model)[1]} ')


if __name__ == '__main__':
    in_args = "--model espnetv2 --s 2.0 --dataset city --data-path /home/john/github/data/cityscapes/ --split val --im-size 1024 512"

    args = load_args(in_args)
    model, device = load_model(args)
    image_list = load_dataset(args)

    evaluate(args, model, image_list, device=device)

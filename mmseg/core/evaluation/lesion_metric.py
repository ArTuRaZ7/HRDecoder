SIGMOID_THRESH = 0.5

#from tkinter import Label
import numpy as np
from sklearn.metrics import auc,roc_auc_score,mean_absolute_error,roc_curve

np.seterr(invalid='ignore')

"""
results:
gt:
[ (2848, 4288),  ...]

results {0, 1, 2, 3 ,4}
gt {0, 1, 2, 3, 4}

0 stands for background
"""


# softmax
def softmax_confused_matrix(pred_label, label, num_classes):
    tp = pred_label[pred_label == label]

    area_p, _ = np.histogram(pred_label, bins=np.arange(num_classes + 1))
    area_tp, _ = np.histogram(tp, bins=np.arange(num_classes + 1))
    area_gt, _ = np.histogram(label, bins=np.arange(num_classes + 1))

    area_fn = area_gt - area_tp

    return area_p, area_tp, area_fn


def softmax_metrics(results, gt_seg_maps, num_classes):
    """
    :param results:  {0, 1, 2, 3 ,4}
    """
    num_imgs = len(results)
    assert len(gt_seg_maps) == num_imgs

    total_p = np.zeros((num_classes,), dtype=np.float64)
    total_tp = np.zeros((num_classes,), dtype=np.float64)
    total_fn = np.zeros((num_classes,), dtype=np.float64)
    maupr = np.zeros((num_classes,), dtype=np.float64)
    mae=np.zeros((num_classes,),dtype=np.float64)

    for i in range(num_imgs):
        if isinstance(results[i], tuple):
            result = results[i][0]
            result = np.argmax(result, axis=0)
        else:
            result = results[i]

        p, tp, fn = softmax_confused_matrix(result, gt_seg_maps[i], num_classes)
        total_p += p
        total_tp += tp
        total_fn += fn

    return total_p, total_tp, total_fn, maupr,mae


# sigmoid
def sigmoid_confused_matrix(pred_logit, raw_label, num_classes, thresh):
    assert pred_logit.shape[0] == num_classes - 1

    class_p = np.zeros((num_classes,), dtype=np.float64)
    class_tp = np.zeros((num_classes,), dtype=np.float64)
    class_fn = np.zeros((num_classes,), dtype=np.float64)
    class_tn = np.zeros((num_classes,),dtype=np.float64)

    for i in range(1, num_classes):
        pred = pred_logit[i - 1] > thresh
        label = raw_label == i 
        class_tp[i] = np.sum(label & pred)
        class_p[i] = np.sum(pred)
        class_fn[i] = np.sum(label) - class_tp[i]
        class_tn[i] = np.sum((label | pred)==0)

    return class_p, class_tp, class_fn, class_tn


def sigmoid_ae(results,gt_seg_maps,num_classes):
    num_imgs = len(results)
    assert len(gt_seg_maps) == num_imgs 

    total_ae = np.zeros((num_classes,),dtype=np.float64)

    for i in range(num_imgs):
        if isinstance(results[i],tuple):
            pred_logit=results[i][0]
        else:
            pred_logit=results[i]

        class_ae = np.zeros((num_classes,),dtype=np.float64)
        
        for j in range(1,num_classes):
            label = gt_seg_maps[i]==j
            class_ae[j] = mean_absolute_error(label,pred_logit[j-1])
        
        total_ae += class_ae

    return total_ae/num_imgs


def sigmoid_metrics(results, gt_seg_maps, num_classes, compute_aupr=False):
    num_imgs = len(results)
    assert len(gt_seg_maps) == num_imgs 

    if compute_aupr: 
        threshs = np.linspace(0, 1, 11)  # 0.1
    else:
        threshs = [SIGMOID_THRESH]

    total_p_list = []
    total_tp_list = []
    total_fn_list = []
    total_tn_list=[]

    for thresh in threshs:
        total_p = np.zeros((num_classes,), dtype=np.float64)
        total_tp = np.zeros((num_classes,), dtype=np.float64)
        total_fn = np.zeros((num_classes,), dtype=np.float64)
        total_tn = np.zeros((num_classes,), dtype=np.float64)

        for i in range(num_imgs):
            if isinstance(results[i], tuple):
                result = results[i][0]
            else:
                result = results[i]

            p, tp, fn,tn = sigmoid_confused_matrix(result, gt_seg_maps[i], num_classes, thresh)
            total_p += p
            total_tp += tp
            total_fn += fn
            total_tn += tn

        total_p_list.append(total_p)
        total_tp_list.append(total_tp)
        total_fn_list.append(total_fn)
        total_tn_list.append(total_tn)

    if len(threshs) > 1: 
        index = int(np.argmax(threshs == SIGMOID_THRESH))
    else:
        index = 0

    total_p = total_p_list[index]
    total_tp = total_tp_list[index]
    total_fn = total_fn_list[index]
    total_tn = total_tn_list[index]

    mae = np.zeros((num_classes,),dtype=np.float64)
    maupr = np.zeros((num_classes,), dtype=np.float64)
    total_p_list = np.stack(total_p_list)
    total_tp_list = np.stack(total_tp_list)
    total_fn_list = np.stack(total_fn_list)
    total_tn_list = np.stack(total_tn_list)

    ppv_list = np.nan_to_num(total_tp_list / total_p_list, nan=1)
    s_list = np.nan_to_num(total_tp_list / (total_tp_list + total_fn_list), nan=0)

    if compute_aupr:
        for i in range(1, len(maupr)):
            x = s_list[:, i]
            y = ppv_list[:, i]
            maupr[i] = auc(x, y)

    mae = sigmoid_ae(results,gt_seg_maps,num_classes)

    return total_p, total_tp, total_fn, maupr, mae


def lesion_metrics(results, gt_seg_maps, num_classes, ignore_index=None, nan_to_num=None):
    """
    :param results: feature map after sigmoid of softmax
    """

    compute_aupr = False
    use_sigmoid = False

    if isinstance(results[0], tuple):
        _, use_sigmoid, compute_aupr = results[0]

    if not use_sigmoid:
        total_p, total_tp, total_fn, maupr, mae = softmax_metrics(
            results, gt_seg_maps, num_classes)
    else:
        total_p, total_tp, total_fn, maupr, mae = sigmoid_metrics(
            results, gt_seg_maps, num_classes, compute_aupr)

    ppv = total_tp / total_p     
    s = total_tp / (total_tp + total_fn)  
    f1 = 2 * total_tp / (total_p + total_tp + total_fn) 
    # f1 = (s * ppv * 2) / (s + ppv)
    iou = total_tp / (total_p + total_fn)

    if nan_to_num is not None:
        return np.nan_to_num(iou, nan=nan_to_num), \
               np.nan_to_num(f1, nan=nan_to_num), \
               np.nan_to_num(ppv, nan=nan_to_num), \
               np.nan_to_num(s, nan=nan_to_num), \
               np.nan_to_num(maupr, nan=nan_to_num), \
               np.nan_to_num(mae,nan=nan_to_num)
    else:
        return iou, f1, ppv, s, maupr, mae


if __name__ == '__main__':
    shape = [3, 4]
    num_classes = 4  # include background
    num = 2
    use_sigmoid = True
    aupr = False

    pred = [(np.random.random([num_classes, shape[0], shape[1]]), use_sigmoid, aupr) for i in range(num)]
    label = [np.random.randint(0, num_classes + 1, shape) for i in range(num)]

    res = lesion_metrics(pred, label, num_classes + 1)
    for i in res: print(i)

    # x = np.random.random(10)
    # y = np.random.random(10)
    # print(auc(x, y))
    # print(roc_auc_score(x, y))
